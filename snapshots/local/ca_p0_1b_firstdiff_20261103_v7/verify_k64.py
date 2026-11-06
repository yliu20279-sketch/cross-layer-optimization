import json
from pathlib import Path
import numpy as np
from core.artifacts import TargetArtifactStore

root=Path('runs')
manifest=json.loads(Path('contracts/qwen15_tensor_inventory.json').read_text())
store=TargetArtifactStore(list(manifest['objects'].values()),'F16')
def array(name):
    obj=store.objects[name]
    raw=store.read(name,0,obj['bytes'])
    return np.frombuffer(raw,dtype='<f2').reshape(obj['shape']),obj

report={}
for req in ('request_a','request_b'):
    ref=root/f'qwen15_frozen_{req}'/'pinned_cpu_reference'
    for phase in ('prefill','decode'):
        stages=root/'qwen15_dual01'/'stages'/req/phase
        x=np.fromfile(ref/f'{phase}_input_norm.bin',dtype='<f2').astype(np.float32)
        for proj in ('q_proj','k_proj','v_proj'):
            name=f'model.layers.0.self_attn.{proj}'
            w,obj=array(name+'.weight')
            if obj['layout']!='input_major':
                w=w.T
            w=w.astype(np.float32)
            bias,_=array(name+'.bias')
            expected=np.fromfile(ref/f'{phase}_{proj}.bin',dtype='<u2')
            acc=np.zeros(w.shape[1],dtype=np.float32)
            for k0 in range(0,len(x),64):
                dot=np.zeros_like(acc)
                for k in range(k0,min(k0+64,len(x))):
                    dot=np.add(dot,np.multiply(x[k],w[k],dtype=np.float32),dtype=np.float32)
                acc=np.add(acc,dot,dtype=np.float32)
            pre_round=np.add(acc,bias.astype(np.float32),dtype=np.float32)
            k64=pre_round.astype(np.float16).view(np.uint16)
            target=np.concatenate([np.fromfile(stages/f'R{rank}_{proj}.bin',dtype='<u2') for rank in range(4)])
            assert target.shape==expected.shape==k64.shape
            for rank in range(4):
                norm=np.fromfile(stages/f'R{rank}_input_norm.bin',dtype='<f2').astype(np.float32)
                assert np.array_equal(norm.view(np.uint32),x.view(np.uint32))
            differing=np.flatnonzero(k64!=expected)
            report[f'{req}/{phase}/{proj}']={
                'elements':int(target.size),
                'target_vs_k64':int(np.count_nonzero(target!=k64)),
                'target_vs_eager':int(np.count_nonzero(target!=expected)),
                'k64_vs_eager_witnesses':[
                    {'element':int(i),'k64_accumulator_hex':f'{acc.view(np.uint32)[i]:08x}',
                     'k64_biased_f32_hex':f'{pre_round.view(np.uint32)[i]:08x}',
                     'target_fp16_hex':f'{target[i]:04x}','k64_fp16_hex':f'{k64[i]:04x}',
                     'eager_fp16_hex':f'{expected[i]:04x}'} for i in differing]
            }
print(json.dumps(report,indent=2))

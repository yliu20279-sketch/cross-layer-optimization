import json
from pathlib import Path
import numpy as np
import torch
from core.artifacts import TargetArtifactStore

root=Path('runs')
manifest=json.loads(Path('contracts/qwen15_tensor_inventory.json').read_text())
store=TargetArtifactStore(list(manifest['objects'].values()),'F16')
def array(name):
    obj=store.objects[name]
    raw=store.read(name,0,obj['bytes'])
    return np.frombuffer(raw,dtype='<f2').reshape(obj['shape']),obj
result={}
for req in ('request_a','request_b'):
    directory=root/f'qwen15_frozen_{req}'/'pinned_cpu_reference'
    for phase in ('prefill','decode'):
        x=np.fromfile(directory/f'{phase}_input_norm.bin',dtype='<f2').astype(np.float32)
        for projection in ('q_proj','k_proj','v_proj'):
            name=f'model.layers.0.self_attn.{projection}'
            weight,obj=array(name+'.weight')
            if obj['layout']!='input_major':
                weight=weight.T
            w=weight.astype(np.float32)
            bias,_=array(name+'.bias')
            b=bias.astype(np.float32)
            expected=np.fromfile(directory/f'{phase}_{projection}.bin',dtype='<u2')
            partial=np.zeros(w.shape[1],np.float32)
            for start in range(0,len(x),64):
                acc=np.zeros_like(partial)
                for i in range(start,min(start+64,len(x))):
                    acc+=x[i]*w[i]
                partial+=acc
            float_linear=torch.nn.functional.linear(torch.from_numpy(x),torch.from_numpy(w.T.copy()),
                                                   torch.from_numpy(b.copy())).numpy()
            candidates={'K64_bias_before_round':partial+b,
                        'K64_bias_after_round':partial.astype(np.float16).astype(np.float32)+b,
                        'torch_F32_then_F16':float_linear,
                        'FP64_dot_then_F16':x.astype(np.float64)@w.astype(np.float64)+b}
            result[f'{req}/{phase}/{projection}']={
                key:int(np.count_nonzero(val.astype(np.float16).view(np.uint16)!=expected))
                for key,val in candidates.items()}
print(json.dumps(result,indent=2))

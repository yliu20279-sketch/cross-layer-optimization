"""Explicit bounded P0-1b correctness-development entry, never a benchmark."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import time
import traceback
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.artifacts import TargetArtifactStore
from core.coupled_backend import LiveBackend,CoupledPayload,CoupledTransport
from core.coupled_layer import CoupledLayer
from core.live_moe import MoEPayloadExecutor
from core.common import require,file_hash
from models.qwen3 import SPEC as Q3
from models.qwen15 import SPEC as Q15

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--model',required=True,choices=['qwen3','qwen15'])
parser.add_argument('--tag',required=True)
parser.add_argument('--timeout',type=int,default=1200)
parser.add_argument('--projection-only',action='store_true')
parser.add_argument('--swap-weight-pages-after-prefill',action='store_true')
parser.add_argument('--allow-correctness-check',required=True,action='store_true')
args=parser.parse_args()
require(args.tag and args.tag.replace('_','').isalnum(),'invalid diagnostic tag')
out=ROOT/'runs'/(args.model+'_'+args.tag);require(not out.exists(),'preserve previous run')
out.mkdir(parents=True)
def read(p):return json.loads(Path(p).read_text())
def save(name,obj):(out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def progress(event,**extra):
    with (out/'PROGRESS.jsonl').open('a') as f:f.write(json.dumps({'event':event,'wall_time':time.time(),**extra})+'\n')
spec=Q3 if args.model=='qwen3' else Q15;dtype='BF16' if args.model=='qwen3' else 'F16'
config=read(ROOT/('upstream/'+args.model+'_config.json'))
require(spec['norm_topk_prob']==config['norm_topk_prob'],'source routing mismatch')
manifest=read(ROOT/'contracts/qwen3_target_manifest.json') if args.model=='qwen3' else list(read(ROOT/'contracts/qwen15_tensor_inventory.json')['objects'].values())
store=TargetArtifactStore(manifest,dtype)
build=read(ROOT/'evidence/COUPLED_BUILD_04.json');codec=read(ROOT/'evidence/REMOTE_BUILD_LIVE_02.json')
launch=json.loads(next(x['text'] for x in read(ROOT/'evidence/NATIVE_SOURCE_INPUTS.json') if x['path'].endswith('backend_launch.json')))
placement={'method':'diagnostic-static-profile-table-not-author-2gram','ep':spec['ep'],'experts':spec['experts'],
    'layers':{str(i):{'expert_to_rank':{str(e):e%spec['ep'] for e in range(spec['experts'])},
                     'token_to_rank':{'17':0,'19':1}} for i in range(spec['layers'])}}
save('PROTOCOL.json',{'model':spec['id'],'dtype':dtype,'config_sha256':file_hash(ROOT/('upstream/'+args.model+'_config.json')),
    'norm_topk_prob':spec['norm_topk_prob'],'scope':'diagnostic hidden-state layer0 TP/EP prefill1 cached-decode1',
    'expert_accumulation':'ascending_expert_id',
    'matrix_precision_contract':'increasing-K64 FP32 partials' if dtype=='F16' else 'preserved BF16 FDA64 primitive',
    'projection_only':args.projection_only,'original_model_oracle_verified':False,'formal_performance':False,
    'fixed_diagnostic_page_swap_after_prefill':args.swap_weight_pages_after_prefill,
    'CPU_PCIe_costs_verified':False,'serial_driver_not_performance_schedule':True,'placement':placement,
    'code_sha256':{str(p.relative_to(ROOT)):file_hash(p) for d in ('core','models') for p in (ROOT/d).rglob('*.py')}})
backend=None
try:
    progress('start')
    backend=LiveBackend(build['binary'],build['sha256'],out/'backend',str(ROOT/'ramulator32.yaml'),timeout=args.timeout)
    native=CoupledPayload(backend,codec['payload_library'],codec['payload_sha256']);transport=CoupledTransport(native)
    helper=MoEPayloadExecutor(spec,store,native,transport,dtype)
    if args.projection_only:
        x=native.encode(np.sin(np.arange(spec['hidden'],dtype='<f4')*.017)*.125,dtype)
        begin=time.monotonic();y=helper._linear(x,'model.layers.0.self_attn.q_proj',0,[0,spec['hidden'],0,128])
        require(np.isfinite(native.decode(y,dtype)).all(),'nonfinite actual Q projection')
        (out/'projection_output.bin').write_bytes(y)
        native.close_weights();summary=backend.close()
        save('RESULT.json',{'status':'PASS_REAL_WEIGHT_COUPLED_PROJECTION_ONLY','summary':summary,
             'wall_seconds':time.monotonic()-begin,'output_sha256':hashlib.sha256(y).hexdigest(),
             'original_model_oracle_verified':False,'formal_performance':False})
    else:

        sessions = {name: CoupledLayer(spec,config,store,native,transport,placement,dtype)
                    for name in ('request_a','request_b')}
        for owner,layer in enumerate(sessions.values(),1):
            layer.request_owner=owner
        trace = []
        outputs = {}
        for pos, phase in enumerate(('prefill','decode')):
            jobs = {}
            for i, (name, layer) in enumerate(sessions.items()):
                hidden = native.encode(np.sin(np.arange(spec['hidden'],dtype='<f4')*.017
                                      + np.float32(pos)*.21 + np.float32(i)*.37)*.125,dtype)
                frozen = ROOT/'frozen_inputs'/args.model/(name+'_'+phase+'_input.bin')
                require(hidden==frozen.read_bytes(),'original input changed')
                hidden=frozen.read_bytes()
                capture_dir=out/'stages'/name/phase
                capture_dir.mkdir(parents=True)
                def capture(rank, stage, raw, directory=capture_dir):
                    (directory/f'R{rank}_{stage}.bin').write_bytes(raw)
                layer.capture=capture
                (out/(name+'_'+phase+'_input.bin')).write_bytes(hidden)
                jobs[name] = layer.forward_steps(hidden,[pos],[17 if i==0 else 19],request_id=name)
            while jobs:
                for name in list(jobs):
                    begin = backend.clock
                    try:
                        rank = next(jobs[name])
                        trace.append({'request':name,'phase':phase,'rank':rank,
                                      'begin_ns':begin,'end_ns':backend.clock})
                    except StopIteration as done:
                        del jobs[name]
                        raw = done.value
                        require(np.isfinite(native.decode(raw,dtype)).all(),'nonfinite output')
                        (out/(name+'_'+phase+'_output.bin')).write_bytes(raw)
                        outputs[name+'_'+phase] = hashlib.sha256(raw).hexdigest()
                    save('REQUEST_TRACE.json',trace)
            handles = set()
            for name, layer in sessions.items():
                require(len(layer.cache)==spec['tp'],'missing rank cache')
                for (which,rank), entry in layer.cache.items():
                    require(entry['length']==pos+1,'incorrect KV length')
                    for member in ('k','v'):
                        handle = entry[member]
                        require(handle not in handles,'aliased KV handle')
                        handles.add(handle)
                        raw = layer._kv_get(handle)
                        (out/f'{name}_{phase}_L{which}_R{rank}_{member}.bin').write_bytes(raw)
                save(name+'_KV_EVENTS.json',layer.kv_events)
                save(name+'_PHASES.json',layer.phases)
            a,b=sessions.values()
            for rank in range(spec['tp']):
                for member in ('k','v'):
                    ah,bh=a.cache[(0,rank)][member],b.cache[(0,rank)][member]
                    expected=a._kv_get(ah)[:256]+b._kv_get(bh)[:256]
                    require(len(expected)==512,'KV batch diagnostic geometry')
                    require(backend.rpc(13,ah,1,bh,2)[3]==512,'KV batch failed')
                    require(backend._read(512)==expected,'paired live KV read mismatch')
            if phase=='prefill':
                layout,generation=backend.layout()
                require(len(layout)>=20 and layout[0,0]==layout[1,0],'invalid migration probe domain')
                candidate=layout[:,:3].copy()
                candidate[0,2],candidate[1,2]=candidate[1,2],candidate[0,2]
                before=backend.clock
                backend.install_layout(candidate,generation,10)
                after=backend.clock
                actual,new_generation=backend.layout()
                require(new_generation==generation+1 and np.array_equal(actual[:,:3],candidate),'mapping commit mismatch')
                save('DUAL_REQUEST_MIGRATION.json',{'before_ns':before,'after_ns':after,
                    'generation_before':generation,'generation_after':new_generation,
                    'prefill_complete_ns':{name:layer.phases[-1]['complete'] for name,layer in sessions.items()},
                    'fixed_diagnostic_swap':True,'cpu_pcie_cache_cost_verified':False})
        migration=read(out/'DUAL_REQUEST_MIGRATION.json')
        require(max(migration['prefill_complete_ns'].values())<=migration['before_ns']
                <=migration['after_ns']<=min(layer.phases[-1]['start'] for layer in sessions.values()),
                'migration escaped dual-request dependency window')
        for layer in sessions.values():
            layer.close()
        native.close_weights()
        summary = backend.close()
        save('RESULT.json',{'status':'INTERLEAVED_RANK_PROBE_COMPLETE',
             'outputs':outputs,'summary':summary,'formal_performance':False,
             'p0_1b_complete':False,'independent_reference_verified':False})
    progress('finished')
    print(json.dumps({'model':args.model,'status':read(out/'RESULT.json')['status'],'formal_performance':False}))
except BaseException:
    (out/'FAILURE.txt').write_text(traceback.format_exc())
    if backend is not None and not backend.closed:backend.abort()
    raise

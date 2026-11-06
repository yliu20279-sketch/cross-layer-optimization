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
from core.coupled_decoder import DecoderSlice
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
    'norm_topk_prob':spec['norm_topk_prob'],'scope':'diagnostic layers 5 and 6 PP boundary prefill1 cached-decode1',
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
        layer=CoupledLayer(spec,config,store,native,transport,placement,dtype)
        layer.request_owner=1
        outputs=[]
        for phase,position,token in [('prefill',0,17),('decode',1,19)]:
            progress('phase_start',phase=phase,target_ns=backend.clock)
            hidden=native.encode(np.sin(np.arange(spec['hidden'],dtype='<f4')*.017+np.float32(position)*.21)*.125,dtype)
            (out/(phase+'_input.bin')).write_bytes(hidden)
            decoder=DecoderSlice(layer)
            result=decoder.forward(hidden,[position],[token],5,7)
            save('PP_'+phase+'.json',decoder.events)
            require(len(result)==spec['hidden']*2 and np.isfinite(native.decode(result,dtype)).all(),'invalid layer result')
            (out/(phase+'_output.bin')).write_bytes(result);outputs.append(hashlib.sha256(result).hexdigest())
            save('PHASES.json',layer.phases);save('KV_EVENTS.json',layer.kv_events)
            save('NUMERIC_CALLS.json',native.calls);save('SOFTWARE_SERVICES.json',native.software);save('TRANSPORT.json',transport.events)
            save('PUBLICATIONS.json',native.publications);save('RPC_EVENTS.json',backend.events)
            # Preserve all current K/V payloads and physical handles, not just a
            # metadata claim about cached context.
            kv=[]
            for (which,rank),entry in layer.cache.items():
                for member in ('k','v'):
                    raw=layer._kv_get(entry[member]);name=phase+'_L%d_R%d_%s.bin'%(which,rank,member)
                    (out/name).write_bytes(raw);kv.append({'rank':rank,'member':member,'length':entry['length'],
                        'handle':entry[member],'file':name,'sha256':hashlib.sha256(raw).hexdigest()})
            save(phase+'_KV_PAYLOADS.json',kv)
            progress('phase_complete',phase=phase,target_ns=backend.clock,output_sha256=outputs[-1])
            if phase=='prefill' and args.swap_weight_pages_after_prefill:
                rows,generation=backend.layout();require(len(rows)>=20,'too few mutable pages for fixed diagnostic swap')
                require(rows[0,0]==rows[1,0],'diagnostic swap must stay within one bound tensor')
                candidate=rows[:,:3].copy();candidate[0,2],candidate[1,2]=candidate[1,2],candidate[0,2]
                backend.install_layout(candidate,generation,10)
                following,new_generation=backend.layout();require(np.array_equal(following[:,:3],candidate),'physical map differs')
                save('MAPPING_PROTOCOL.json',{'kind':'fixed two-page correctness permutation, not trained CA optimization',
                    'generation_before':generation,'generation_after':new_generation,'domain_pages':len(rows),
                    'changed_rows_before':rows[:2].tolist(),'changed_rows_after':following[:2].tolist(),
                    'changed_valid_bytes':8192,'budget_percent':10,'full_B_CA_numerical_pair':False})
                progress('fixed_diagnostic_map_installed',target_ns=backend.clock)
        require(len(layer.phases)==4 and all(x['past']==1 and x['length']==2 for x in layer.kv_events if x['past']>0),'decode did not append real KV prefix')
        layer.close();native.close_weights();summary=backend.close()
        save('RESULT.json',{'status':'PASS_LIVE_COUPLED_LAYER_GRAPH_LIMITED','model':spec['id'],'dtype':dtype,
            'TP':spec['tp'],'EP':spec['ep'],'phases':layer.phases,'summary':summary,
            'complete_layer_payload_graph':True,'original_model_numerics_verified':False,
            'host_software_CPU_and_PCIe_costs_verified':False,'serial_driver_not_performance_schedule':True,
            'formal_performance_runs':0,'complete_model_forwards':0,'GPU_runs':0})
    progress('finished')
    print(json.dumps({'model':args.model,'status':read(out/'RESULT.json')['status'],'formal_performance':False}))
except BaseException:
    (out/'FAILURE.txt').write_text(traceback.format_exc())
    if backend is not None and not backend.closed:backend.abort()
    raise

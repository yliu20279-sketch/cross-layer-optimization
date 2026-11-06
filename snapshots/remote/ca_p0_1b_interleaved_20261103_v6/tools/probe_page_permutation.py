"""Actual physical migration + unchanged real-weight primitive result."""
from pathlib import Path
import hashlib
import json
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.coupled_backend import LiveBackend,CoupledPayload
from core.artifacts import TargetArtifactStore
from core.live_moe import MoEPayloadExecutor
from core.common import require
from models.qwen15 import SPEC
def read(p):return json.loads(Path(p).read_text())
build=read(ROOT/'evidence/COUPLED_BUILD_04.json');codec=read(ROOT/'evidence/REMOTE_BUILD_LIVE_02.json')
launch=json.loads(next(x['text'] for x in read(ROOT/'evidence/NATIVE_SOURCE_INPUTS.json') if x['path'].endswith('backend_launch.json')))
out=ROOT/'physical_permutation_probe01'
b=LiveBackend(build['binary'],build['sha256'],out,launch['controls']['HB_RAM_CONFIG'],timeout=120)
try:
    n=CoupledPayload(b,codec['payload_library'],codec['payload_sha256'])
    store=TargetArtifactStore(list(read(ROOT/'contracts/qwen15_tensor_inventory.json')['objects'].values()),'F16')
    helper=MoEPayloadExecutor(SPEC,store,n,None,'F16')
    x=n.encode(np.sin(np.arange(2048,dtype='<f4')*.017)*.125,'F16')
    before=helper._linear(x,'model.layers.0.self_attn.q_proj',0,[0,2048,0,128])
    layout,generation=b.layout();require(len(layout)>=20,'insufficient page pool for 10% move budget')
    require(layout[0,0]==layout[1,0],'probe expects two pages of the same bound tensor')
    handle=int(layout[0,0]);p0=int(layout[0,1]);p1=int(layout[1,1])
    a=b.get(handle,4096,p0*4096);c=b.get(handle,4096,p1*4096)
    require(a!=c,'identical diagnostic pages would not prove physical payload migration')
    candidate=layout[:,:3].copy();candidate[0,2],candidate[1,2]=candidate[1,2],candidate[0,2]
    b.install_layout(candidate,expected_generation=generation,budget_percent=10)
    actual,following=b.layout();require(following==generation+1 and np.array_equal(actual[:,:3],candidate),'new physical map not installed')
    require(b.get(handle,4096,p0*4096)==a and b.get(handle,4096,p1*4096)==c,'logical page payload changed after real migration')
    after=helper._linear(x,'model.layers.0.self_attn.q_proj',0,[0,2048,0,128])
    require(before==after,'actual primitive output changed after legal weight-page permutation')
    (out/'LAYOUT_BEFORE.json').write_text(json.dumps(layout.tolist()))
    (out/'LAYOUT_AFTER.json').write_text(json.dumps(actual.tolist()))
    (out/'RPC_EVENTS.json').write_text(json.dumps(b.events))
    (out/'output_before.f16').write_bytes(before);(out/'output_after.f16').write_bytes(after)
    n.close_weights();summary=b.close()
    require(summary['mapping_installs']==1 and summary['migration_write_bytes']==8192,'migration byte ledger differs')
    result={'status':'PASS_ACTUAL_PHYSICAL_WEIGHT_MIGRATION_AND_NUMERIC_INVARIANCE_PROBE_ONLY',
       'binary_sha256':build['sha256'],'mapping_generation':following,'moved_valid_bytes':8192,
       'weight_pool_valid_bytes':len(layout)*4096,'source_pages_differ':True,'output_bitwise_equal':True,
       'output_sha256':hashlib.sha256(before).hexdigest(),'summary':summary,'formal_performance_runs':0,
       'full_model_or_full_CA_layer_test':False,'CPU_query_and_install_control_cost_verified':False}
    (ROOT/'evidence/PHYSICAL_PERMUTATION_PROBE.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
except BaseException:
    if not b.closed:b.abort()
    raise

# Negative controls are independent fail-stop process attempts. Keep every
# failed target entry and never continue using a partially rejected context.
negatives=[]
for index,kind in enumerate(['alias','fixed_object','stale_generation','over_budget']):
    case=ROOT/('physical_permutation_negative_%d'%index)
    target=LiveBackend(build['binary'],build['sha256'],case,launch['controls']['HB_RAM_CONFIG'],timeout=30)
    movable=target.stage(0,b'A'*8192,role=1);fixed=target.stage(0,b'R'*4096,role=2)
    rows,gen=target.layout();candidate=rows[:,:3].copy();expected=gen
    if kind=='alias':candidate[1,2]=candidate[0,2]
    elif kind=='fixed_object':candidate[1,0]=fixed
    elif kind=='stale_generation':expected=gen+1
    else:candidate[0,2],candidate[1,2]=candidate[1,2],candidate[0,2]
    rejected=False
    try:target.install_layout(candidate,expected,10)
    except RuntimeError as error:
        rejected=True;message=str(error)
    finally:
        if not target.closed:target.abort()
    require(rejected,'illegal physical map admitted: '+kind)
    negatives.append({'kind':kind,'rejected':True,'message':message})
(ROOT/'evidence/PHYSICAL_PERMUTATION_NEGATIVES.json').write_text(json.dumps({'cases':negatives,'formal_performance_runs':0},indent=2))
print(json.dumps({'negative_cases':len(negatives),'all_rejected':True}))

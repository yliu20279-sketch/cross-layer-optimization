"""Cross-object physical migration and PP4 payload service probes only."""
from pathlib import Path
import json
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.coupled_backend import LiveBackend,CoupledPayload,CoupledTransport
from core.common import require
def read(p):return json.loads(Path(p).read_text())
build=read(ROOT/'evidence/COUPLED_BUILD_04.json');codec=read(ROOT/'evidence/REMOTE_BUILD_LIVE_02.json')
launch=json.loads(next(x['text'] for x in read(ROOT/'evidence/NATIVE_SOURCE_INPUTS.json') if x['path'].endswith('backend_launch.json')))
b=LiveBackend(build['binary'],build['sha256'],ROOT/'cross_object_pp_probe01',launch['controls']['HB_RAM_CONFIG'],timeout=60)
try:
    a=b.stage(0,b'A'*(32*4096),role=1);c=b.stage(0,b'B'*(32*4096),role=1)
    router=b.stage(0,b'R'*4096,role=2)
    rows,gen=b.layout();left=int(np.flatnonzero(rows[:,0]==a)[0]);right=int(np.flatnonzero(rows[:,0]==c)[0])
    candidate=rows[:,:3].copy();candidate[left,2],candidate[right,2]=candidate[right,2],candidate[left,2]
    b.install_layout(candidate,gen,10)
    require(b.get(a,4096)==b'A'*4096 and b.get(c,4096)==b'B'*4096,'cross-object weight payload corrupted')
    require(b.get(router)==b'R'*4096,'fixed router moved/corrupted')
    b.free(a);workspace=b.stage(0,b'W'*4096)
    require(b.get(c,4096)==b'B'*4096,'new workspace aliased another remapped live object')
    b.free(workspace);b.free(router);b.free(c)
    n=CoupledPayload(b,codec['payload_library'],codec['payload_sha256']);transport=CoupledTransport(n)
    payload=np.arange(2048,dtype='<u2').tobytes()
    for src,dst in [(0,4),(4,8),(8,12)]:payload=transport.send(src,dst,0,'PP4_payload_boundary_probe',payload)
    require(payload==np.arange(2048,dtype='<u2').tobytes(),'PP4 boundary changed activation bytes')
    summary=b.close()
    result={'status':'PASS_CROSS_OBJECT_PHYSICAL_LIFETIME_AND_PP4_PAYLOAD_PROBE_ONLY','summary':summary,
        'cross_object_weight_swap_valid_bytes':8192,'fixed_router_unchanged':True,
        'new_workspace_did_not_alias_remapped_weight':True,'PP_boundaries':transport.events,
        'full_24_layer_PP_model_verified':False,'formal_performance_runs':0}
    (ROOT/'evidence/CROSS_OBJECT_PP_PROBE.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({'status':result['status'],'transactions':summary['transactions'],'PP_boundaries':3,'packets':summary['packets']}))
except BaseException:
    if not b.closed:b.abort()
    raise

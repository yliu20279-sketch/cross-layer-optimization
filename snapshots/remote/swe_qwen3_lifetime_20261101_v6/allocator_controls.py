import ctypes as C,json
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent;u=C.CDLL(str(R/'libcpu_probe.so'));U=C.c_uint64;u.serve.argtypes=[U,C.c_void_p,U,C.c_void_p,U,U,U,U]
def svc(kind,a=0,b=0,c=0,n=32,refuse=False):
 out=np.zeros(n,dtype='u1');rc=u.serve(kind,None,0,out.ctypes.data,n,a,b,c)
 if refuse:assert rc==-1;return
 assert rc==0;return out.view('<u8')
base=32*2**20;v=svc(24,64,100000,2);assert v[0]==base;version=int(v[1])
svc(24,64,100000,1,refuse=True)
svc(25,100000,version+1,0,refuse=True)
svc(25,100000,version,1,refuse=True)
assert svc(25,100000,version,0)[2]==1
assert svc(26,1,n=48)[0]==0
other=svc(24,64,100001,0);assert other[0]==base+64
assert svc(25,100000,version,0)[2]==0
svc(26,0,n=32,refuse=True)
assert svc(26,2,n=64)[0]==2
svc(25,100000,version,0,refuse=True)
new=svc(24,64,100000,1);assert new[0]==base and new[1]!=version
svc(25,100000,version,0,refuse=True)
svc(24,0,100002,0,refuse=True);svc(24,209*2**20,100002,0,refuse=True);svc(24,208*2**20,100002,0,refuse=True)
assert svc(25,100000,int(new[1]),0)[2]==0
assert svc(26,1,n=48)[0]==1
out=dict(state='PASS_LIMITED_C_ALLOCATOR_CONTROLS',checked=['live_range_not_reused','duplicate_live_id_refused','wrong_version_refused','premature_zero_reader_release_refused','outstanding_reader_prevents_barrier_reclaim','barrier_output_capacity_refused_without_mutation','completed_reader_waits_for_barrier','reused_address_has_new_version','stale_version_after_reuse_refused','zero_size_refused','oversize_refused','arena_exhaustion_refused'],target_native_runs=0,physical_runs=0)
(R/'ALLOCATOR_CONTROLS.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))

import ctypes as C,json,os
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/('case'+os.environ['SWE_RUN_ROUND']);D.mkdir(exist_ok=True)
u=C.CDLL(str(R/'libfull.so'));U=C.c_uint64
u.um_init.argtypes=[C.c_char_p];u.um_error.restype=C.c_char_p
u.um_store.argtypes=[U,C.c_void_p,U];u.um_load.argtypes=[U,C.c_void_p,U]
u.um_recv.argtypes=[C.c_void_p,U];u.um_send.argtypes=[C.c_void_p,U]
u.um_software.argtypes=[U,C.c_void_p,U,C.c_void_p,U,U,U,U]
def ck(rc):assert rc==0,u.um_error()
def svc(kind,a=0,b=0,c=0,words=4):
 out=(U*words)();ck(u.um_software(kind,None,0,out,C.sizeof(out),a,b,c));return tuple(out)
ck(u.um_init(str(D).encode()));previous=None;events=[]
for phase in range(2):
 data=(C.c_ubyte*32)();ck(u.um_recv(data,32))
 address,version,_,_=svc(24,32,phase,1)
 assert svc(27,phase,version)[2]==1
 ck(u.um_store(address,data,32));loaded=(C.c_ubyte*32)();ck(u.um_load(address,loaded,32));assert bytes(data)==bytes(loaded)
 assert svc(25,phase,version)[2]==0
 if previous:
  assert svc(28,*previous)[2]==0
  reclaimed=svc(26,2,words=8);assert reclaimed[0]==1 and reclaimed[4]==previous[0]
 else:assert svc(26,2,words=8)[0]==0
 ck(u.um_send(loaded,32));previous=(phase,version);events.append(dict(phase=phase,address=address,version=version))
if os.environ.get('SWE_LEAK_OWNER')=='1':
 rc=u.um_finalize();raise AssertionError(('leaked owner must never receive successful acknowledgement',rc))
assert svc(28,*previous)[2]==0
assert svc(26,2,words=8)[0]==1
assert svc(29)==(0,0,0,208*2**20)
ck(u.um_finalize());ck(u.um_shutdown())
(D/'ENDPOINT_ROOT_PASS.json').write_text(json.dumps(dict(state='PASS_ENDPOINT_ONLY_NOT_MODEL',events=events,teardown_ack=True),indent=2))

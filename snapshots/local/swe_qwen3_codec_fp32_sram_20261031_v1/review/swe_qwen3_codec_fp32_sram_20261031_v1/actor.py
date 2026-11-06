import os,ctypes as C,json,hashlib
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent;out=R/('case'+os.environ['SWE_RUN_ROUND'])/'N00';out.mkdir(exist_ok=False)
u=C.CDLL(str(R/'libactor.so'));U=C.c_uint64
for name in ['um_recv','um_send']:getattr(u,name).argtypes=[C.c_void_p,U]
for name in ['um_store','um_load']:getattr(u,name).argtypes=[U,C.c_void_p,U]
u.um_init.argtypes=[C.c_char_p];u.um_sram_gate.argtypes=[U,U,U,C.c_char_p];u.um_error.restype=C.c_char_p;u.um_now.restype=U
def ck(rc):
 if rc:raise RuntimeError(u.um_error().decode())
def recv(n):
 a=np.empty(n,dtype='u1')
 for off in range(0,n,65536):ck(u.um_recv(a[off:].ctypes.data,min(65536,n-off)))
 return a
def sha(a):return hashlib.sha256(a.tobytes()).hexdigest()
ck(u.um_init(str(out).encode()));header=recv(64).view('<u8');rank,e,t,K,N,wb,ib,dtype=map(int,header)
assert (rank,K,N,wb,ib,dtype)==(0,2048,768,3145728,4096,0x00040003)
sizes=[ib,2*ib,wb,2*wb];addrs=[0,8*2**20,65536,16*2**20];bodies=[]
for n,addr in zip(sizes,addrs):
 a=recv(n);ck(u.um_store(addr,a.ctypes.data,n));back=np.empty_like(a);ck(u.um_load(addr,back.ctypes.data,n));assert np.array_equal(a,back);bodies.append(back)
for raw,expanded in [(bodies[0],bodies[1]),(bodies[2],bodies[3])]:assert np.array_equal(raw.view('<u2').astype('<u4')<<16,expanded.view('<u4'))
metadata_ready=int(u.um_now());ck(u.um_sram_gate(addrs[1],addrs[3],32*2**20,str(out).encode()));compute_done=int(u.um_now())
y=np.empty(N,dtype='<f4');ck(u.um_load(32*2**20,y.ctypes.data,y.nbytes));(out/'actual_fp32.bin').write_bytes(y.tobytes());ck(u.um_send(y.ctypes.data,y.nbytes));returned=int(u.um_now());ck(u.um_shutdown())
(out/'RESULT.json').write_text(json.dumps(dict(state='PASS_CPU_EXPANSION_CONSUMED_AND_FP32_RETURNED',metadata_ready=metadata_ready,compute_done=compute_done,returned=returned,input_sha256=sha(bodies[0]),weight_sha256=sha(bodies[2]),expanded_input_sha256=sha(bodies[1]),expanded_weight_sha256=sha(bodies[3]),output_sha256=sha(y),precision='original BF16; FP32 temporary and primitive execution; CPU BF16 RNE'),indent=2))

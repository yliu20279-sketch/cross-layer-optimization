import os,ctypes as C,json,hashlib
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent;B=R.parent;rank=int(os.environ['SWE_RANK']);out=R/('case'+os.environ['SWE_RUN_ROUND'])/('N%02d'%rank);out.mkdir(parents=True,exist_ok=False)
u=C.CDLL(str(R/'libactor.so'));U=C.c_uint64
for name in ['um_recv','um_send']:getattr(u,name).argtypes=[C.c_void_p,U]
for name in ['um_store','um_load']:getattr(u,name).argtypes=[U,C.c_void_p,U]
u.um_init.argtypes=[C.c_char_p];u.um_compute.argtypes=[U,C.c_int,C.c_char_p];u.um_error.restype=C.c_char_p;u.um_now.restype=U
def ck(rc):
 if rc:raise RuntimeError(u.um_error().decode())
def recv(n):
 a=np.empty(n,dtype='u1');ck(u.um_recv(a.ctypes.data,n));return a
def digest(a):return hashlib.sha256(a.tobytes()).hexdigest()
ck(u.um_init(str(out).encode()));header=recv(64).view('<u8');r,e,t,K,N,wb,ib,dtype=map(int,header);assert (r,K,N,wb,ib,dtype)==(rank,2048,768,768*2048*2,4096,3)
x=recv(ib);ck(u.um_store(0,x.ctypes.data,ib));wh=hashlib.sha256()
for off in range(0,wb,65536):
 a=recv(min(65536,wb-off));wh.update(a.tobytes());ck(u.um_store(65536+off,a.ctypes.data,a.size))
actual_x=np.empty(ib,dtype='u1');ck(u.um_load(0,actual_x.ctypes.data,ib));assert np.array_equal(x,actual_x)
lib=C.CDLL(str(B/'swe_qwen3_step3_four_gates_20261028_v1/libsource_gemm_v2.so'));lib.source_gemm.argtypes=[C.c_void_p]*3+[C.c_int]*3
y=np.empty(N,dtype='<f4');last_reader=[];read_weight_hash=hashlib.sha256()
for n0 in range(0,N,64):
 wt=np.empty(64*K*2,dtype='u1');ck(u.um_load(65536+n0*K*2,wt.ctypes.data,wt.size));last_reader.append(int(u.um_now()));read_weight_hash.update(wt.tobytes())
 assert lib.source_gemm(actual_x.ctypes.data,wt.ctypes.data,y[n0:n0+64].ctypes.data,1,64,K)==0
 ck(u.um_compute(2*64*K,0,b'BF16_gate_FP32_vector_proxy'))
assert read_weight_hash.hexdigest()==wh.hexdigest()
codec=C.CDLL(str(B/'swe_qwen3_bf16_functional_v1_20261026/libbf16_codec_bridge.so'));codec.swe_bf16_encode.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t]
bits=np.empty(N,dtype='<u2');codec.swe_bf16_encode(y.ctypes.data,bits.ctypes.data,N);commit=int(u.um_now());ck(u.um_store(4*2**20,bits.ctypes.data,bits.nbytes));back=np.empty_like(bits);ck(u.um_load(4*2**20,back.ctypes.data,back.nbytes));assert np.array_equal(bits,back)
(out/'actual.bin').write_bytes(back.tobytes());ck(u.um_send(back.ctypes.data,back.nbytes));returned=int(u.um_now());ck(u.um_shutdown())
(out/'RESULT.json').write_text(json.dumps(dict(state='COMPUTED_RETURNED',rank=rank,expert=e,token=t,weight_sha256=wh.hexdigest(),HB_weight_sha256=read_weight_hash.hexdigest(),input_sha256=digest(x),output_sha256=digest(back),weight_last_reader=max(last_reader),compute_done=commit,returned=returned,HB_capacity=512*2**20,output_address=4*2**20,scope='one real selected expert full gate projection; CPU numeric and generic vector proxy, not native BF16 array'),indent=2))

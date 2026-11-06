import os,ctypes as C,json,hashlib
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent;B=R.parent;rank=int(os.environ['SWE_RANK']);out=R/('case'+os.environ['SWE_RUN_ROUND'])/('N%02d'%rank);out.mkdir(parents=True,exist_ok=False)
u=C.CDLL(str(R/'libfull.so'));U=C.c_uint64
for name in ['um_net_recv','um_net_send']:getattr(u,name).argtypes=[C.c_void_p,U]
for name in ['um_store','um_load']:getattr(u,name).argtypes=[U,C.c_void_p,U]
u.um_matrix.argtypes=[U,U,U,U,U,U,U,C.c_char_p];u.um_init.argtypes=[C.c_char_p];u.um_compute.argtypes=[U,C.c_int,C.c_char_p];u.um_error.restype=C.c_char_p;u.um_now.restype=U
lib=C.CDLL(str(B/'swe_qwen3_step3_four_gates_20261028_v1/libsource_gemm_v2.so'));lib.source_gemm.argtypes=[C.c_void_p]*3+[C.c_int]*3
params=json.loads((R/'PARAMETERS.json').read_text());history=[]
def ck(rc):
 if rc:raise RuntimeError(u.um_error().decode())
def recv(n):
 a=np.empty(n,dtype='u1');ck(u.um_net_recv(a.ctypes.data,n));return a
def recv_to_hb(n,addr):
 # This large array is a functional mirror of committed HB, not SRAM staging.
 shadow=np.empty(n,dtype='u1')
 for off in range(0,n,65536):
  a=recv(min(65536,n-off));ck(u.um_store(addr+off,a.ctypes.data,a.size));shadow[off:off+a.size]=a
 return shadow
def digest(a):return hashlib.sha256(a.tobytes()).hexdigest()
ck(u.um_init(str(out).encode()))
while True:
 header=recv(64).view('<u8');cmd,tag,M,N,K,ib,wb,owner=map(int,header)
 if cmd==9:break
 assert cmd==2 and owner==rank and ib==2*M*K and wb==2*N*K
 p=params[tag&0xffffffff];assert p['id']==tag&0xffffffff and p['owner']==rank and p['bytes']==wb and p['shape']==[N,K]
 start=int(u.um_now());x=recv_to_hb(ib,32*2**20);xf=recv_to_hb(ib*2,320*2**20);wh=hashlib.sha256()
 for off in range(0,wb,65536):
  a=recv(min(65536,wb-off));wh.update(a.tobytes());ck(u.um_store(off,a.ctypes.data,a.size))
 assert wh.hexdigest()==p['sha256'];wf=recv_to_hb(wb*2,256*2**20)
 assert np.array_equal(x.view('<u2').astype('<u4')<<16,xf.view('<u4'))
 for off in range(0,wb,65536):
  a=np.empty(min(65536,wb-off),dtype='u1');ck(u.um_load(off,a.ctypes.data,a.size));assert np.array_equal(a.view('<u2').astype('<u4')<<16,wf[off*2:(off+a.size)*2].view('<u4'))
 actual_x=x;rh=wh;ck(u.um_matrix(320*2**20,256*2**20,324*2**20,M,N,K,tag>>32,str(out).encode()));compute=int(u.um_now());last=json.loads((out/"LOWERING.jsonl").read_text().splitlines()[-1])["last_reader"]
 back=np.empty((M,N),dtype='<f4');ck(u.um_load(324*2**20,back.ctypes.data,back.nbytes))
 ck(u.um_net_send(back.ctypes.data,back.nbytes));history.append(dict(sequence=tag>>32,param=p['id'],owner=rank,M=M,N=N,K=K,weight_sha256=rh.hexdigest(),input_sha256=digest(actual_x),output_sha256=digest(back),start=start,weight_last_reader=last,compute_done=compute,returned=int(u.um_now())))
ck(u.um_shutdown());(out/'JOBS.json').write_text(json.dumps(history,indent=2))

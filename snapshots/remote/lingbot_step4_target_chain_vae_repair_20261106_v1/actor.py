
import os,json,ctypes as C
from pathlib import Path
import torch,numpy as np
R=Path(__file__).resolve().parent;B=R.parent
p=R/'ROUND_N00';k=int(p.read_text())+1 if p.exists() else 1;p.write_text(str(k))
D=R/f'case{k}';D.mkdir(exist_ok=True);N=D/'N00';N.mkdir()
u=C.CDLL(str(R/'libpeer.so'));U=C.c_uint64
u.um_init.argtypes=[C.c_char_p];u.um_error.restype=C.c_char_p;u.um_now.restype=U
for n in ('um_store','um_sram_load'):getattr(u,n).argtypes=[U,C.c_void_p,U]
for n in ('um_net_send','um_net_recv'):getattr(u,n).argtypes=[C.c_void_p,U]
def ck(rc):
 if rc:raise RuntimeError(u.um_error().decode())
def hb(a,addr):
 b=np.empty_like(a);ck(u.um_store(addr,a.ctypes.data,a.nbytes));ck(u.um_sram_load(addr,b.ctypes.data,b.nbytes));assert a.tobytes()==b.tobytes();return b
def rx(n):
 a=np.empty(n,np.uint8);ck(u.um_net_recv(a.ctypes.data,n));return a
def tx(a):ck(u.um_net_send(a.ctypes.data,a.nbytes))
def load(p):return torch.load(p,weights_only=True).float().numpy()
ck(u.um_init(str(N).encode()))
C0=B/'lingbot_step4_cfg_scheduler_20261105_v2'
V=B/'lingbot_step4_cfg_scheduler_20261105_v3'
log=[]
for op in (0,1):
 if op==0:
  a=np.stack([load(C0/(n+'.pt'))[:,:,:2,:8,:8] for n in ('cond_prediction','uncond_prediction','scheduler_input_latent')]).copy().view(np.uint8).reshape(-1)
 else:
  # Explicit reference injection bridges unexecuted steps 1..39.
  a=load(B/'lingbot_steps1_2_20261027_v1/attempt2/latent_40step.pt')[:,:,:1].copy().view(np.uint8).reshape(-1)
 start=int(u.um_now());a=hb(a,0)
 header=np.array([op,k,a.nbytes,0,0,0,0,0],np.uint64);tx(header);tx(a)
 response=rx(64).view(np.uint64);assert response[0]==op and response[1]==k and response[2]==a.nbytes
 out=rx(int(response[3]));receive_done=int(u.um_now())
 # Consumer uses the returned tensor only after actual receive and HB completion.
 out=hb(out,32*2**20);consumer=int(u.um_now());assert consumer>=receive_done
 (N/f'output{op}.bin').write_bytes(out.tobytes())
 if op==0:
  refs=np.stack([load(V/(n+'.pt'))[:,:,:2,:8,:8] for n in ('cfg_CPU','scheduler_CPU','next_latent_CPU')]).copy()
  assert out.tobytes()==refs.tobytes()
 if op==1:
  ref=np.load(B/'lingbot_step4_vae_20261105_v1/frames_FP32.npy',mmap_mode='r')[0]
  assert out.tobytes()==ref.astype('<f4').tobytes(), 'VAE frozen GPU first-frame bitwise mismatch'
 log.append(dict(op=op,start_ns=start,receive_done_ns=receive_done,consumer_ns=consumer,bytes=out.nbytes))
ck(u.um_sram_finish());ck(u.um_shutdown())
(N/'EVENTS.json').write_text(json.dumps(log,indent=2))
(N/'PASS.json').write_text(json.dumps(dict(state='PASS_TARGET_HB_COMM_AND_CPU_BOUNDARIES',cfg_scheduler_elements_per_stage=2048,vae_first_frame_values=480*832*3)))

from pathlib import Path
import ctypes,subprocess,json,torch,numpy as np
R=Path(__file__).resolve().parent
subprocess.run(['g++','-O3','-ffp-contract=off','-fno-fast-math','-shared','-fPIC',str(R/'sdpa_candidate.cpp'),'-o',str(R/'sdpa_candidate.so')],check=True)
l=ctypes.CDLL(str(R/'sdpa_candidate.so'));l.scores.argtypes=[ctypes.c_void_p]*3+[ctypes.c_int]*3;l.attn.argtypes=[ctypes.c_void_p]*4+[ctypes.c_int]*6
p=torch.load(R/'SDPA_INPUT.pt',weights_only=True);q=p['q'][0,0,:8].contiguous();k=p['k'].contiguous();v=p['v'].contiguous();ref=p['GPU'][0,0,:8].contiguous();M,D=q.shape;N=k.shape[-2];s=torch.empty(M,N);l.scores(q.data_ptr(),k.data_ptr(),s.data_ptr(),M,N,D)
t=np.memmap('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4/sfu_profile/ex2_all_f32.raw',dtype=np.float32,mode='r');rows=[]
import os
os.environ['CUDA_VISIBLE_DEVICES']='1'
from torch.nn.attention import sdpa_kernel,SDPBackend
for n in [128,256,384,512,6240]:
 with sdpa_kernel(SDPBackend.EFFICIENT_ATTENTION):ref=torch.nn.functional.scaled_dot_product_attention(q[None,None].cuda(),p['k'][:,:,:n].cuda(),p['v'][:,:,:n].cuda()).cpu()[0,0]
 for lanes,ln in [(8,4)]:
  for mode in [0,1]:
   y=torch.empty_like(q);ss=s[:,:n].contiguous();l.attn(ss.data_ptr(),v.data_ptr(),y.data_ptr(),t.ctypes.data,M,n,D,lanes,ln,mode);rows.append(dict(keys=n,mode=mode,diff=int((y.view(torch.int32)!=ref.view(torch.int32)).sum()),max_abs=float((y-ref).abs().max())))
(R/'SDPA_PREFIX_CANDIDATES.json').write_text(json.dumps(rows,indent=2));print(rows)

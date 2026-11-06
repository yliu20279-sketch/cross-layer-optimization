import os
os.environ['CUDA_VISIBLE_DEVICES']=''
import ctypes as C,torch,numpy as np,json
from pathlib import Path
R=Path(__file__).resolve().parent;torch.set_num_threads(1);torch.manual_seed(20261029);lib=C.CDLL(str(R/'libsoftmax.so'));lib.sm_input.argtypes=[C.c_void_p]*4+[C.c_int]*3;rows=[]
for K in [19,20,128]:
 for M in [1,19,513]:
  for dtype in [torch.bfloat16,torch.float32]:
   for kind in ['random','uniform','range','mask']:
    x=torch.randn(M,K)*8 if kind in ['random','mask'] else (torch.zeros(M,K) if kind=='uniform' else torch.linspace(-100,100,K).expand(M,K).contiguous())
    if kind=='mask':x[:,K//2:]=torch.finfo(torch.bfloat16).min
    x=x.to(dtype);y=np.empty((M,K),dtype='<f4');ex=np.empty_like(y);s=np.empty(M*3,dtype='<f4');assert lib.sm_input(x.data_ptr(),y.ctypes.data,s.ctypes.data,ex.ctypes.data,M,K,int(dtype==torch.bfloat16))==0
    gold=torch.softmax(x,dim=-1,dtype=torch.float32);different=int((gold!=torch.from_numpy(y)).sum());v=dict(K=K,M=M,dtype=str(dtype),kind=kind,elements=x.numel(),different=different);rows.append(v);assert different==0,v
(R/'CONTROL_RESULTS.json').write_text(json.dumps(rows,indent=2));print('CONTROL_PASS',len(rows),sum(v['elements'] for v in rows))

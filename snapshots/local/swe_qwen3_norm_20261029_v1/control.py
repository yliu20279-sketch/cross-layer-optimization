import ctypes as C,torch,numpy as np,json
from pathlib import Path
R=Path(__file__).resolve().parent;torch.set_num_threads(1);torch.manual_seed(20261029)
l=C.CDLL(str(R/'libnorm.so'));l.rms.argtypes=[C.c_void_p]*3+[C.c_int]*2+[C.c_float]
rows=[]
for K in [128,2048]:
 for M in [1,19,513]:
  for kind in ['random','zeros','constant']:
   x=(torch.randn(M,K)*0.25).bfloat16() if kind=='random' else torch.full((M,K),0.0 if kind=='zeros' else 0.125,dtype=torch.bfloat16)
   y=np.empty((M,K),dtype='<u2');s=np.empty(3*M,dtype='<f4');assert l.rms(x.data_ptr(),y.ctypes.data,s.ctypes.data,M,K,1e-6)==0
   f=x.float();v=f.pow(2).mean(-1,keepdim=True);e=v+1e-6;i=torch.rsqrt(e);n=(f*i).bfloat16()
   for name,a,b in [('variance',v,torch.from_numpy(s[:M]).reshape(M,1)),('epsilon',e,torch.from_numpy(s[M:2*M]).reshape(M,1)),('rsqrt',i,torch.from_numpy(s[2*M:]).reshape(M,1)),('normalized_BF16',n,torch.from_numpy(y).view(torch.bfloat16))]:
    c=dict(K=K,M=M,kind=kind,stage=name,elements=a.numel(),different=int((a!=b).sum()));rows.append(c);assert c['different']==0,c
(R/'CONTROL_RESULTS.json').write_text(json.dumps(rows,indent=2));print('CONTROL_PASS',len(rows),sum(v['elements'] for v in rows))

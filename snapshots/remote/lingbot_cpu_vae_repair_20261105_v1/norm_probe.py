
import os,json
os.environ['CUDA_VISIBLE_DEVICES']='1'
import torch,numpy as np
from pathlib import Path
torch.set_num_threads(4)
R=Path(__file__).resolve().parent
d=torch.load(R/'NEXT_OPERATOR.pt',weights_only=True)
x=d['args'][0];g=d['state']['gamma'];eps=1e-12
def diff(a,b):return dict(different=int((a.contiguous().view(torch.int32)!=b.contiguous().view(torch.int32)).sum()),maxabs=float((a-b).abs().max()))
cn=torch.linalg.vector_norm(x,ord=2,dim=1,keepdim=True)
gn=torch.linalg.vector_norm(x.cuda(),ord=2,dim=1,keepdim=True).cpu()
c=x/cn;ref=(x.cuda()/gn.cuda()).cpu()
scale=float(x.shape[1]**.5)
out=dict(shape=list(x.shape),strides=x.stride(),norm=diff(cn,gn),division_given_same_denominator=diff(x/gn,ref),scale_gamma_given_same_normalized=diff(ref*scale*g,(ref.cuda()*scale*g.cuda()).cpu()),norms_CPU=cn.reshape(-1)[:8].tolist(),norms_GPU=gn.reshape(-1)[:8].tolist())
torch.save(dict(x=x,normGPU=gn,normCPU=cn),R/'NORM_DATA.pt')
(R/'NORM_PROBE.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out))

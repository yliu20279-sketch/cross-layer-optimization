import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
import hashlib,json,sys
from pathlib import Path
import numpy as np
import torch
from safetensors import safe_open
torch.set_num_threads(1);R=Path(__file__).resolve().parent;B=R.parent;D=R/'batch_attempt2';D.mkdir(exist_ok=False)
M=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B');index=json.loads((M/'model.safetensors.index.json').read_text())['weight_map']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for n,h in json.loads((R/'BATCH_V2_FREEZE.json').read_text()).items():assert sha(R/n)==h
root=B/'swe_qwen3_step3_gpu_20261026_v1/requests/R0002';fp=root/'layer0_actual_fixtures.pt';manifest=json.loads((root/'MANIFEST.json').read_text());assert sha(fp)==next(v['sha256'] for v in manifest if v['path']==fp.name)
fixture=torch.load(fp,weights_only=True,map_location='cpu')
def weight(expert,proj):
 key='model.layers.0.mlp.experts.%d.%s.weight'%(expert,proj)
 with safe_open(str(M/index[key]),framework='pt',device='cpu') as f:return f.get_tensor(key)
def inputs(x,w):return x.float().numpy(),w.float().numpy()
def bits(a):
 u=np.ascontiguousarray(a,dtype='<f4').view('<u4');return ((u+np.uint32(0x7fff)+((u>>16)&1))>>16).astype('<u2')
def candidate(x,w,mode):
 x,w=inputs(x,w);s=np.zeros((x.shape[0],w.shape[0]),dtype='<f4');c=np.zeros_like(s)
 for k in range(x.shape[1]):
  p=x[:,k,None]*w[None,:,k]
  if mode=='sequential':s=s+p
  elif mode=='kahan':
   y=p-c;t=s+y;c=(t-s)-y;s=t
  else:raise ValueError(mode)
 return s
cases=[]
for phase,f in fixture.items():
 ids=f['actual_selected_experts'];h=f['moe_input']
 for expert in sorted(set(ids.flatten().tolist())):
  slots,tokens=torch.where(ids.T==expert);cases.append((phase,int(expert),tokens.tolist(),h[tokens]))
# Additional non-dispatch test: same generic rule over all20 rows of expert49.
cases.append(('all20_control',49,list(range(20)),torch.cat([fixture['prefill']['moe_input'],fixture['decode']['moe_input']])))


def generic(x,w):
 xf,wf=inputs(x,w);M,K=xf.shape;N=wf.shape[0]
 if M==1:
  lanes=np.zeros((64,N),dtype='f4')
  for k in range(K):lanes[k%64]=lanes[k%64]+xf[0,k]*wf[:,k]
  for off in [32,16,8,4,2,1]:lanes[:off]=lanes[:off]+lanes[off:2*off]
  return lanes[0:1]
 bk=K if K<=384 else ((K+1)//2 if K<1536 else 768)
 total=None
 for k0 in range(0,K,bk):
  out=np.zeros((M,N),dtype='f4');end=min(K,k0+bk)
  for k in range(k0,end,2):
   for q in [k+1,k]:
    if q<end:out=out+xf[:,q,None]*wf[None,:,q]
  total=out if total is None else total+out
 return total

results=[]
for phase,e,tokens,x in cases:
 for proj in ['gate_proj','up_proj','down_proj']:
  w=weight(e,proj);arg=x if proj!='down_proj' else torch.nn.functional.silu(torch.nn.functional.linear(x,weight(e,'gate_proj')))*torch.nn.functional.linear(x,weight(e,'up_proj'));ref=torch.nn.functional.linear(arg,w).view(torch.uint16).numpy();out=bits(generic(arg,w));results.append(dict(phase=phase,expert=e,projection=proj,M=x.shape[0],elements=ref.size,different=int(np.count_nonzero(out!=ref))))
s=dict(state='PASS_LIMITED_SOURCE_ORDER_BATCH' if not any(v['different'] for v in results) else 'PARTIAL_SOURCE_ORDER_BATCH',algorithm='M1 AVX2 64lane; M>1 oneDNN BF16 emulation oddK-before-evenK with source bk/get_k_padd split',cases=len(results),elements=sum(v['elements'] for v in results),different=sum(v['different'] for v in results),results=results)
(D/'RESULTS.json').write_text(json.dumps(s,indent=2));print(json.dumps({k:v for k,v in s.items() if k!='results'}))

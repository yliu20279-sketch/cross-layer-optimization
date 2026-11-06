import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
import hashlib,json,sys
from pathlib import Path
import numpy as np
import torch
from safetensors import safe_open
torch.set_num_threads(1);R=Path(__file__).resolve().parent;B=R.parent;D=R/'tree_cpu_attempt1';D.mkdir(exist_ok=False)
M=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B');index=json.loads((M/'model.safetensors.index.json').read_text())['weight_map']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for n,h in json.loads((R/'CPU_FREEZE.json').read_text()).items():assert sha(R/n)==h
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

def tree(x,w):
 xf,wf=inputs(x,w);assert xf.shape[0]==1 and xf.shape[1]==2048
 s=np.zeros((128,wf.shape[0]),dtype='f4')
 for k in range(2048):s[k%128]=s[k%128]+xf[0,k]*wf[:,k]
 for offset in [64,32,16,8,4,2,1]:s[:offset]=s[:offset]+s[offset:2*offset]
 return s[0:1]
for n,h in json.loads((R/'TREE_FREEZE.json').read_text()).items():assert sha(R/n)==h
results=[];batch_differences=0
for phase,expert,tokens,x in cases:
 w=weight(expert,'gate_proj');out=[];different=0
 for i in range(x.shape[0]):
  ref=torch.nn.functional.linear(x[i:i+1],w).view(torch.uint16).numpy();b=bits(tree(x[i:i+1],w));different+=int(np.count_nonzero(b!=ref));out.append(b)
 batchref=torch.nn.functional.linear(x,w).view(torch.uint16).numpy();cross=int(np.count_nonzero(np.concatenate(out)!=batchref));batch_differences+=cross
 results.append(dict(phase=phase,expert=expert,tokens=tokens,rows=x.shape[0],outputs=x.shape[0]*768,single_token_source_different=different,batch_source_different=cross))
summary=dict(state='PASS_LIMITED_M1_SOURCE_TREE' if not any(v['single_token_source_different'] for v in results) else 'FAIL_M1_SOURCE_TREE',cases=len(results),outputs=sum(v['outputs'] for v in results),single_token_source_different=sum(v['single_token_source_different'] for v in results),batch_source_different=batch_differences,contract='Only M1 AVX512 PyTorch2.6 source GEMV; no batch GEMM promotion; all BF16 bitwise',results=results,up='NOT_RUN')
(D/'RESULTS.json').write_text(json.dumps(summary,indent=2));print(json.dumps({k:v for k,v in summary.items() if k!='results'}))

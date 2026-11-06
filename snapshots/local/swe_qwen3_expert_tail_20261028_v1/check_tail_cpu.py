import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
import hashlib,json,sys
from pathlib import Path
import numpy as np
import torch
from safetensors import safe_open
torch.set_num_threads(1);R=Path(__file__).resolve().parent;B=R.parent;D=R/'cpu_tail_attempt1';D.mkdir(exist_ok=False)
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


def tree1(x,w):
 xf,wf=inputs(x,w);s=np.zeros((64,wf.shape[0]),dtype='f4')
 for k in range(xf.shape[1]):s[k%64]=s[k%64]+xf[0,k]*wf[:,k]
 for off in [32,16,8,4,2,1]:s[:off]=s[:off]+s[off:2*off]
 return s[0:1]
results=[]
for phase,expert,tokens,x in cases:
 wg=weight(expert,'gate_proj');wu=weight(expert,'up_proj');wd=weight(expert,'down_proj');diffs=dict(silu=0,product=0,down=0)
 for row in range(x.shape[0]):
  gate=torch.nn.functional.linear(x[row:row+1],wg);up=torch.nn.functional.linear(x[row:row+1],wu);g=gate.float().numpy()
  with np.errstate(over='ignore'):s=bits(g/(np.float32(1)+np.exp(-g,dtype=np.float32)))
  sr=torch.nn.functional.silu(gate);diffs['silu']+=int(np.count_nonzero(s!=sr.view(torch.uint16).numpy()))
  sv=torch.from_numpy(s.copy()).view(torch.bfloat16);pv=bits(sv.float().numpy()*up.float().numpy());pr=sr*up
  diffs['product']+=int(np.count_nonzero(pv!=pr.view(torch.uint16).numpy()))
  prod=torch.from_numpy(pv.copy()).view(torch.bfloat16);down=bits(tree1(prod,wd));ref=torch.nn.functional.linear(pr,wd)
  diffs['down']+=int(np.count_nonzero(down!=ref.view(torch.uint16).numpy()))
 results.append(dict(phase=phase,expert=expert,rows=x.shape[0],differences=diffs))
summary=dict(state='PASS_LIMITED_M1_TAIL_CPU' if not any(any(v['differences'].values()) for v in results) else 'PARTIAL_TAIL_CPU',cases=len(results),rows=sum(v['rows'] for v in results),differences={k:sum(v['differences'][k] for v in results) for k in ['silu','product','down']},scope='fixed CPU source M1 only, not batch/GPU/NPU-exp certification',results=results)
(D/'RESULTS.json').write_text(json.dumps(summary,indent=2));print(json.dumps({k:v for k,v in summary.items() if k!='results'}))

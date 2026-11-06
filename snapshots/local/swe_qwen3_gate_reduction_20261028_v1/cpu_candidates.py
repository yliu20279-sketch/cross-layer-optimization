import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
import hashlib,json,sys
from pathlib import Path
import numpy as np
import torch
from safetensors import safe_open
torch.set_num_threads(1);R=Path(__file__).resolve().parent;B=R.parent;D=R/'cpu_attempt1';D.mkdir(exist_ok=False)
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
results=[]
for phase,expert,tokens,x in cases:
 w=weight(expert,'gate_proj');ref=torch.nn.functional.linear(x,w).view(torch.uint16).numpy();row=dict(phase=phase,expert=expert,tokens=tokens,shape=list(ref.shape))
 for mode in ['sequential','kahan']:
  out=candidate(x,w,mode);b=bits(out);row[mode]=dict(different=int(np.count_nonzero(b!=ref)),outputs=int(ref.size))
  if phase=='prefill' and expert==49:
   np.save(D/(mode+'_expert49_FP32.npy'),out)
 results.append(row)
gate_pass=all(v['kahan']['different']==0 for v in results)
summary=dict(state='PASS_LIMITED_CPU_KAHAN_GATE' if gate_pass else 'PARTIAL_KAHAN_GATE_SOURCE_DIFFERENCES',algorithm='generic FP32 Kahan; exact BF16 products; no FMA; no per-output branches; BF16 RNE',cases=len(results),gate_outputs=sum(v['kahan']['outputs'] for v in results),sequential_different=sum(v['sequential']['different'] for v in results),kahan_different=sum(v['kahan']['different'] for v in results),gate_pass=gate_pass,results=results,up='NOT_RUN',GPU_runs=0,softmax_FP32='FAILED_RETAINED')
(D/'RESULTS.json').write_text(json.dumps(summary,indent=2));print(json.dumps({k:v for k,v in summary.items() if k!='results'}))

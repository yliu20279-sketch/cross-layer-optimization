import os
os.environ['CUDA_VISIBLE_DEVICES']='0'
os.environ['OMP_NUM_THREADS']='1'
import hashlib,json,inspect
from pathlib import Path
import torch
import torch.nn.functional as F
from safetensors import safe_open
import transformers.models.qwen3_moe.modeling_qwen3_moe as source
R=Path(__file__).resolve().parent; O=R/'attempt1';O.mkdir(exist_ok=False)
B=R.parent; M=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B')
torch.set_num_threads(1);torch.set_num_interop_threads(1)
torch.backends.cuda.matmul.allow_tf32=False
torch.backends.cuda.matmul.allow_bf16_reduced_precision_reduction=False
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  while x:=f.read(8*1024*1024):h.update(x)
 return h.hexdigest()
def raw(x):return x.contiguous().view(torch.uint8).numpy().tobytes()
def dump(n,x):(O/n).write_text(json.dumps(x,indent=2))
freeze=json.loads((R/'FREEZE.json').read_text());assert all(sha(R/n)==h for n,h in freeze.items())
fp=B/'swe_qwen3_step3_gpu_20261026_v1/requests/R0002/layer0_actual_fixtures.pt'
assert sha(fp)=='f78c166c14c6690f7482c7a26952adfefe265b5655aeed2b4b69d0049c6ac11f'
assert sha(inspect.getsourcefile(source))=='3af43d01f9f902c8009b6dd7d7b8b563561b53dd0aa54175f585ae90d049fdb8'
idx=json.loads((M/'model.safetensors.index.json').read_text())['weight_map'];weights={}
keys=['input_layernorm.weight','post_attention_layernorm.weight','mlp.gate.weight']+['self_attn.'+s+'.weight' for s in ['q_proj','k_proj','v_proj','o_proj','q_norm','k_norm']]
shards=sorted({idx['model.layers.0.'+k] for k in keys});mv={v['path']:v for v in json.loads((M.parent.parent/'MODEL_VERIFICATION.json').read_text())}
for shard in shards:
 assert sha(M/shard)==mv[shard]['sha256']
 with safe_open(str(M/shard),framework='pt',device='cpu') as f:
  for k in keys:
   if idx['model.layers.0.'+k]==shard:weights[k]=f.get_tensor('model.layers.0.'+k)
assert all(w.dtype==torch.bfloat16 for w in weights.values())
f=torch.load(fp,map_location='cpu',weights_only=True)['prefill'];trace={};files=[];checks=[]
def compare(label,a,b,scope):
 a=a.cpu();b=b.cpu();mask=a!=b;loc=mask.nonzero();v=dict(name=label,scope=scope,shape=list(a.shape),dtype=str(a.dtype),different=int(mask.sum()),exact=torch.equal(a,b),max_abs=float((a.float()-b.float()).abs().max()),first_indices=loc[:12].tolist());checks.append(v);return v
def run(device):
 d={};w={k:v.to(device) for k,v in weights.items()}
 def put(n,t):d[n]=t.detach().cpu().clone();return t
 def norm(x,scale,p):
  a=put(p+'.cast',x.float());sq=put(p+'.square',a.pow(2));v=put(p+'.variance',sq.mean(-1,keepdim=True));v=put(p+'.epsilon',v+1e-6);inv=put(p+'.rsqrt',torch.rsqrt(v));z=put(p+'.normalized_fp32',a*inv);z=put(p+'.normalized_bf16',z.to(torch.bfloat16));return put(p+'.output',scale*z)
 x=put('input',f['decoder_input'].to(device));h=norm(x,w['input_layernorm.weight'],'input_norm')
 q=put('q_proj',F.linear(h,w['self_attn.q_proj.weight']));k=put('k_proj',F.linear(h,w['self_attn.k_proj.weight']));v=put('v_proj',F.linear(h,w['self_attn.v_proj.weight']))
 q=norm(q.view(1,19,32,128),w['self_attn.q_norm.weight'],'q_norm').transpose(1,2);k=norm(k.view(1,19,4,128),w['self_attn.k_norm.weight'],'k_norm').transpose(1,2);v=v.view(1,19,4,128).transpose(1,2)
 cos=f['cos'].to(device).unsqueeze(1);sin=f['sin'].to(device).unsqueeze(1)
 def rotate(x):a,b=x.chunk(2,dim=-1);return torch.cat((-b,a),-1)
 q=put('q_rope',q*cos+rotate(q)*sin);k=put('k_rope',k*cos+rotate(k)*sin)
 k=k.repeat_interleave(8,dim=1);v=v.repeat_interleave(8,dim=1)
 scores=put('qk_matmul',torch.matmul(q,k.transpose(2,3)));scores=put('scaled_scores',scores*(128**-0.5));mask=torch.full((1,1,19,19),torch.finfo(torch.bfloat16).min,dtype=torch.bfloat16,device=device);mask.masked_fill_(torch.arange(19,device=device)[None,None,None,:]<=torch.arange(19,device=device)[None,None,:,None],0);scores=put('masked_scores',scores+mask)
 p=put('softmax_fp32',F.softmax(scores,dim=-1,dtype=torch.float32));p=put('softmax_bf16',p.bfloat16());c=put('pv_matmul',torch.matmul(p,v));c=c.transpose(1,2).contiguous().reshape(1,19,4096);out=put('attention_output',F.linear(c,w['self_attn.o_proj.weight']));res=put('attention_residual',x+out);h=norm(res,w['post_attention_layernorm.weight'],'post_norm');logits=put('router_logits',F.linear(h,w['mlp.gate.weight']));p=put('router_softmax_fp32',F.softmax(logits.reshape(-1,128),dim=-1,dtype=torch.float32));val,ids=torch.topk(p,8,dim=-1);put('route_IDs',ids);put('route_weights',(val/val.sum(-1,keepdim=True)).bfloat16())
 return d
with torch.inference_mode():
 trace['cpu']=run('cpu');trace['gpu']=run('cuda:0')
 for n in trace['cpu']:compare(n,trace['cpu'][n],trace['gpu'][n],'free_running_CPU_vs_GPU')
 compare('GPU_attention_vs_original_capture',trace['gpu']['attention_output'],f['attention_output'],'capture_identity')
 compare('GPU_moe_input_vs_original_capture',trace['gpu']['post_norm.output'].reshape_as(f['moe_input']),f['moe_input'],'capture_identity')
 compare('GPU_logits_vs_original_capture',trace['gpu']['router_logits'].reshape_as(f['router_logits']),f['router_logits'],'capture_identity')
 compare('GPU_IDs_vs_original_capture',trace['gpu']['route_IDs'],f['actual_selected_experts'],'capture_identity')
 compare('CPU_IDs_vs_original_capture',trace['cpu']['route_IDs'],f['actual_selected_experts'],'original_route_difference')
 # Equal-input probes distinguish local operator differences from propagated differences.
 for origin in ['cpu','gpu']:
  h=trace[origin]['input_norm.output']
  for s in ['q','k','v']:
   w=weights['self_attn.'+s+'_proj.weight'];compare(origin+'_input_'+s+'_linear',F.linear(h,w),F.linear(h.cuda(),w.cuda()),'equal_input_operator_probe')
  for p,key in [('input_norm','input_layernorm.weight'),('q_norm','self_attn.q_norm.weight'),('k_norm','self_attn.k_norm.weight')]:
   a=trace[origin][p+'.cast'];sq=a.pow(2);compare(origin+'_'+p+'_square',sq,a.cuda().pow(2),'equal_input_operator_probe');compare(origin+'_'+p+'_mean',sq.mean(-1,keepdim=True),sq.cuda().mean(-1,keepdim=True),'equal_input_operator_probe');e=trace[origin][p+'.epsilon'];compare(origin+'_'+p+'_rsqrt',torch.rsqrt(e),torch.rsqrt(e.cuda()),'equal_input_operator_probe')
 for dev,d in trace.items():
  for n,t in d.items():
   name=dev+'_'+n+'.bin';(O/name).write_bytes(raw(t));files.append(dict(path=name,stage=n,device=dev,shape=list(t.shape),dtype=str(t.dtype),bytes=len(raw(t)),sha256=sha(O/name)))
dump('CHECKS.json',checks);dump('FILES.json',files)
dump('PROVENANCE.json',dict(fixture_sha256=sha(fp),source_sha256=sha(inspect.getsourcefile(source)),shards={s:sha(M/s) for s in shards},torch=torch.__version__,GPU=torch.cuda.get_device_name(),GPU_peak_bytes=torch.cuda.max_memory_allocated(),threads=torch.get_num_threads(),allow_tf32=False,allow_bf16_reduced_precision_reduction=False,scope='bounded external GPU reference operators; no target GPU, full model or agent'))
free=[c for c in checks if c['scope']=='free_running_CPU_vs_GPU'];first=next((c for c in free if c['different']),None)
dump('RESULTS.json',dict(state='DIAGNOSIS_COMPLETE_DIFFERENCES_RETAINED',first_difference=first,capture_identity=[c for c in checks if c['scope']=='capture_identity'],CPU_IDs_vs_original=next(c for c in checks if c['name']=='CPU_IDs_vs_original_capture'),GPU_reference_runs=1,target_native_runs=0,physical_NPU_runs=0,host_GiB=128,HB_GiB=8,precision='original BF16 with source FP32 boundaries',softmax_FP32='RETAINED'))
print(json.dumps(json.loads((O/'RESULTS.json').read_text())))

import ctypes as C,hashlib,json,subprocess,sys,traceback
from pathlib import Path
import torch
torch.set_num_threads(1);torch.set_num_interop_threads(1)
R=Path(__file__).resolve().parent;O=R/'attempt1';O.mkdir(exist_ok=False);B=R.parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):p.write_text(json.dumps(v,indent=2))
try:
 freeze=json.loads((R/'PRE_RUN_FREEZE.json').read_text());assert all(sha(R/n)==h for n,h in freeze.items())
 cmd=['g++','-std=c++17','-O2','-fno-fast-math','-ffp-contract=off','-fno-tree-vectorize','-shared','-fPIC',str(R/'route_kernel.cpp'),'-o',str(O/'libroute.so')]
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=60);dump(O/'BUILD.json',dict(command=cmd,returncode=p.returncode,stderr=p.stderr));p.check_returncode()
 lib=C.CDLL(str(O/'libroute.so'));lib.select_route128.argtypes=[C.c_void_p]*3+[C.c_size_t];lib.full_route128.argtypes=[C.c_void_p]*4+[C.c_size_t]
 def run(prob=None,logits=None):
  n=(prob if prob is not None else logits).shape[0];ids=torch.empty((n,8),dtype=torch.int64);w=torch.empty((n,8),dtype=torch.bfloat16)
  if logits is not None:
   out=torch.empty((n,128),dtype=torch.float32);rc=lib.full_route128(logits.contiguous().data_ptr(),out.data_ptr(),ids.data_ptr(),w.data_ptr(),n)
  else:out=prob.contiguous();rc=lib.select_route128(out.data_ptr(),ids.data_ptr(),w.data_ptr(),n)
  return rc,out,ids,w
 rows=[];all_logits=[];all_ids=[];all_weights=[];all_prob=[];bindings=[]
 for name,rid in [('swe_qwen3_step3_gpu_20261026_v1','R0002'),('swe_qwen3_step3_development_20261026_v6','R0001')]:
  folder=B/name/'requests'/rid;manifest=json.loads((folder/'MANIFEST.json').read_text());path=folder/'layer0_actual_fixtures.pt'
  assert sha(path)==next(x['sha256'] for x in manifest if x['path']==path.name)
  bindings.append(dict(root=name,request=rid,fixture_sha256=sha(path)))
  fs=torch.load(path,map_location='cpu',weights_only=True);phases=[]
  for phase,f in fs.items():
   if phase=='prefill_chunks':phases.extend((phase+'/'+k,v) for k,v in sorted(f.items(),key=lambda x:int(x[0])))
   else:phases.append((phase,f))
  for phase,f in phases:
   logits=f['router_logits'].contiguous();gp=f['router_probabilities_fp32'].contiguous();gold=f['actual_selected_experts'];gw=f['actual_final_weights']
   rc,_,ids,weights=run(prob=gp);assert rc==0
   rc,prob,fids,fw=run(logits=logits);assert rc==0
   ordered=torch.sort(gp,descending=True).values;boundary=ordered[:,7]==ordered[:,8];internal=(ordered[:,:7]==ordered[:,1:8]).any(-1)
   stable=torch.argsort(gp,descending=True,stable=True)[:,:8]
   row=dict(root=name,request=rid,phase=phase,tokens=logits.shape[0],internal_tie_rows=int(internal.sum()),boundary_tie_rows=int(boundary.sum()),
    captured_probability_selector_ids_exact=torch.equal(ids,gold),captured_probability_selector_bad_rows=int((ids!=gold).any(-1).sum()),
    captured_probability_weights_exact=torch.equal(weights,gw),
    new_softmax_ids_exact=torch.equal(fids,gold),new_softmax_bad_id_rows=int((fids!=gold).any(-1).sum()),new_softmax_weights_exact=torch.equal(fw,gw),
    FP32_probabilities_exact=torch.equal(prob,gp),FP32_probabilities_max_abs=float((prob-gp).abs().max()),
    stable_expert_ID_tie_negative_control_bad_rows=int((stable!=gold).any(-1).sum()))
   rows.append(row);all_logits.append(logits);all_ids.append(gold);all_weights.append(gw);all_prob.append(gp)
 dump(O/'INPUT_BINDINGS.json',bindings)
 logits=torch.cat(all_logits);gold=torch.cat(all_ids);gw=torch.cat(all_weights);gp=torch.cat(all_prob)
 # Real independent expected inputs/outputs saved outside implementation interface.
 (O/'real_logits_BF16.bin').write_bytes(logits.view(torch.uint16).numpy().tobytes())
 (O/'gold_IDs.bin').write_bytes(gold.numpy().tobytes());(O/'gold_weights_BF16.bin').write_bytes(gw.view(torch.uint16).numpy().tobytes())
 rc,np,ni,nw=run(logits=logits);assert rc==0
 (O/'new_IDs.bin').write_bytes(ni.numpy().tobytes());(O/'new_weights_BF16.bin').write_bytes(nw.view(torch.uint16).numpy().tobytes())
 synth=[]
 cases={'uniform':torch.zeros((1,128),dtype=torch.bfloat16),
  'internal_ties':torch.arange(128,dtype=torch.float32).floor_divide(2).reshape(1,128).to(torch.bfloat16),
  'boundary_group':torch.cat([torch.arange(7,dtype=torch.float32)+4,torch.ones(12),torch.full((109,),-10.)]).reshape(1,128).to(torch.bfloat16),
  'underflow':torch.cat([torch.tensor([600.]),torch.full((127,),-600.)]).reshape(1,128).to(torch.bfloat16),
  'signed_zero_logits':torch.tensor([0.,-0.]*64,dtype=torch.bfloat16).reshape(1,128)}
 for name,x in cases.items():
  rc,p,ids,w=run(logits=x);assert rc==0
  rc2,_,ids2,w2=run(prob=p)
  assert rc2==0 and torch.equal(ids,ids2) and torch.equal(w,w2)
  assert torch.unique(ids).numel()==8 and bool(torch.isfinite(p).all()) and bool((p>=0).all())
  synth.append(dict(name=name,repeat_exact=True,IDs=ids.tolist(),weight_sum=float(w.float().sum())))
 guards=[]
 for name,v in [('NaN',float('nan')),('Inf',float('inf'))]:
  x=torch.zeros((1,128),dtype=torch.bfloat16);x[0,0]=v;rc,*_=run(logits=x);assert rc!=0;guards.append(name+'_logit_rejected')
 for name,v in [('negative_probability',-1.),('negative_zero_probability',-0.)]:
  x=torch.ones((1,128),dtype=torch.float32);x[0,0]=v;rc,*_=run(prob=x);assert rc!=0;guards.append(name+'_rejected')
 assert not torch.cuda.is_initialized()
 status=dict(state='FUNCTIONAL_CHECK_COMPLETE_DIFFERENCES_RETAINED',rows=rows,real_tokens=logits.shape[0],synthetic=synth,guards=guards,
  captured_probability_selector_all_exact=all(x['captured_probability_selector_ids_exact'] and x['captured_probability_weights_exact'] for x in rows),
  new_softmax_route_all_exact=all(x['new_softmax_ids_exact'] and x['new_softmax_weights_exact'] for x in rows),
  GPU_FP32_probability_all_exact=all(x['FP32_probabilities_exact'] for x in rows),
  scope='finite E128/k8 host software functional fallback, no new GPU or native NPU events, no injected IDs',
  host_GiB=128,HB_GiB=8,new_GPU_agent_runs=0,physical_NPU_runs=0,CUDA_initialized=False)
 dump(O/'RESULTS.json',status);print(json.dumps(status,indent=2))
except Exception:dump(O/'FAILURE.json',dict(error=traceback.format_exc()));raise

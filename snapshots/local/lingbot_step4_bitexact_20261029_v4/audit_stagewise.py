"""Independent full single-layer audit; no adapter math is imported."""
import os
os.environ['CUDA_VISIBLE_DEVICES']=''
import pathlib,json,hashlib,numpy as np,torch
P=pathlib.Path(__file__).resolve().parent;R=P/'full_layer_stagewise_v1';G=P.parent/'lingbot_step3_capture_20261028_v1';torch.set_num_threads(4);checks=[]
def check(n,b):checks.append(dict(name=n,passed=bool(b)));assert b,n
def desc(d):
 q=P/d['file'];check('path_scope_'+d['file'],q.resolve().is_relative_to(P.resolve()))
 with q.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
 check('SHA_'+d['file'],h==d['sha256']);return q
num=json.loads((R/'RESULT.json').read_text());check('numerical_done',num['status']=='PASS_LIMITED_FULL_SINGLE_LAYER_NUMERICAL_AUDIT_PENDING');check('autonomous_route_batch',num['route_counts_derived_from_autonomous_full_FFN_inputs'] and not num['source_internal_Golden_injected']);total=0
for branch,S in [('cond',49883),('uncond',48986)]:
 d=R/branch;ar=[json.loads(q.read_text()) for q in sorted(d.glob('a_*/PASS.json'),key=lambda q:int(q.parent.name[2:]))];br=[json.loads(q.read_text()) for q in sorted(d.glob('b_*/PASS.json'),key=lambda q:int(q.parent.name[2:]))];check(branch+'_chunk_counts',len(ar)==len(br)==(S+63)//64)
 binding=json.loads((d/'ROUTE_BINDING.json').read_text());check(branch+'_no_Golden_route_input',not binding['source_internal_Golden_injected']);full=np.load(desc(binding['ffn_input']),mmap_mode='r');ids=np.load(desc(binding['ids']));weights=np.load(desc(binding['weights']));check(branch+'_count_binding',np.array_equal(np.bincount(ids.reshape(-1),minlength=128),binding['counts']));gi=torch.load(P/'free_router_validation'/(branch+'_ids.pt'),weights_only=True).numpy();gw=torch.load(P/'free_router_validation'/(branch+'_weights.pt'),weights_only=True).float().numpy();check(branch+'_GPU_route_exact',np.array_equal(ids,gi) and np.array_equal(weights.view(np.uint32),gw.view(np.uint32)))
 for stage in ['attention_output','ffn_input','ffn_output','post_ffn_norm','block_output']:
  gold=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_'+stage+'.pt'),weights_only=True)[0]
  for begin,(a,b) in zip(range(0,S,64),zip(ar,br)):
   check(branch+'_coverage_'+stage+'_'+str(begin),a['begin']==b['begin']==begin and a['end']==b['end']==min(begin+64,S));record=a[stage] if stage in ['attention_output','ffn_input'] else b['files'][stage];candidate=np.load(desc(record));reference=gold[begin:a['end']].float().numpy();check(branch+'_'+stage+'_'+str(begin),candidate.shape==reference.shape and np.array_equal(candidate.view(np.uint32),reference.view(np.uint32)))
 check(branch+'_full_autonomous_ffn_grid',np.all((full.view(np.uint32)&0xffff)==0));total+=S
r=dict(status='PASS_LIMITED_FULL_SINGLE_LAYER_CPU_FUNCTIONAL',query_rows=total,check_count=len(checks),checks=checks,failures=[],target_GPU_count=0,CUDA_initialized=torch.cuda.is_initialized(),host_GiB=128,HB_GiB=8,precision='original mixed BF16/FP32',source_internal_Golden_injected=False,new_target_native_runs=0,physical_NPU_runs=0,scope='same seen layer0/step0 dualCFG full queries and full real K/V, not48layer/40step/VLM/VAE/TI2V/timing');(R/'INDEPENDENT_AUDIT.json').write_text(json.dumps(r,indent=2));(R/'STATUS.json').write_text(json.dumps({k:v for k,v in r.items() if k!='checks'},indent=2));print(json.dumps({k:v for k,v in r.items() if k!='checks'}))

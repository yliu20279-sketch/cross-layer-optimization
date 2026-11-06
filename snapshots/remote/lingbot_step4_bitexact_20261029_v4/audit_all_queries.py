"""Independent full-query verification after numerical job finishes."""
import os
os.environ['CUDA_VISIBLE_DEVICES']=''
import pathlib,json,hashlib,time,numpy as np,torch
P=pathlib.Path(__file__).resolve().parent;D=P/'full_query_acceptance';G=P.parent/'lingbot_step3_capture_20261028_v1';torch.set_num_threads(4);checks=[];total=0
result=json.loads((D/'RESULT.json').read_text());assert result['status']=='PASS_LIMITED_LAYER0_STEP0_ALL_QUERY_ROWS'
def check(n,v):checks.append(dict(name=n,pass_check=bool(v)));assert v,n
def sha(q):
 with q.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
for branch,S in [('cond',49883),('uncond',48986)]:
 records=[json.loads(q.read_text()) for q in sorted(D.glob(branch+'_*/PASS.json'),key=lambda q:int(q.parent.name.split('_')[-1]))];check(branch+'_chunk_count',len(records)==(S+63)//64);expected=0
 goldids=torch.load(P/'free_router_validation'/(branch+'_ids.pt'),weights_only=True).numpy();goldw=torch.load(P/'free_router_validation'/(branch+'_weights.pt'),weights_only=True).float().numpy()
 for r in records:
  check(branch+'_coverage_'+str(expected),r['begin']==expected and r['end']==min(expected+64,S));folder=D/(branch+'_'+str(expected))
  for name,h in r['files'].items():check(branch+'_SHA_'+str(expected)+'_'+name,sha(folder/name)==h)
  check(branch+'_route_'+str(expected),np.array_equal(np.load(folder/'ids.npy'),goldids[r['begin']:r['end']]) and np.array_equal(np.load(folder/'weights.npy').view(np.uint32),goldw[r['begin']:r['end']].view(np.uint32)));expected=r['end']
 check(branch+'_complete_coverage',expected==S);total+=expected
 for label in ['attention_output','ffn_input','ffn_output','post_ffn_norm','block_output']:
  gold=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_'+label+'.pt'),weights_only=True)[0]
  for r in records:
   a=np.load(D/(branch+'_'+str(r['begin']))/(label+'.npy'));b=gold[r['begin']:r['end']].float().numpy();check(branch+'_'+label+'_'+str(r['begin']),a.shape==b.shape and np.array_equal(a.view(np.uint32),b.view(np.uint32)))
check('all_query_rows',total==98869);check('runtime_no_GPU',not torch.cuda.is_initialized() and result['target_GPU_count']==0);check('no_internal_Golden_injected',result['source_internal_Golden_injected']==False)
r=dict(status='PASS_LIMITED_FULL_SINGLE_LAYER_CPU_FUNCTIONAL',query_rows=total,check_count=len(checks),failures=[],checks=checks,target_GPU_count=0,host_GiB=128,HB_GiB=8,precision='original mixed BF16/FP32',new_target_native_runs=0,physical_NPU_runs=0,scope='same seen layer0/step0 dualCFG,all query rows and real full K/V; not48layer/40step/VLM/VAE/TI2V or target timing',source_Golden_internal_injected=False)
(D/'INDEPENDENT_AUDIT.json').write_text(json.dumps(r,indent=2));(D/'STATUS.json').write_text(json.dumps({k:v for k,v in r.items() if k!='checks'},indent=2));print(json.dumps({k:v for k,v in r.items() if k!='checks'}))

"""Read-only reuse audit and geometry admission checks before full CPU resume."""
import os
os.environ['CUDA_VISIBLE_DEVICES']=''
import pathlib,json,hashlib,torch,numpy as np
from batch_adapter import expert_linear
P=pathlib.Path(__file__).resolve().parent;G=P.parent/'lingbot_step3_capture_20261028_v1';torch.set_num_threads(4);checks=[]
def sha(q):
 with q.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def check(n,b):checks.append(dict(name=n,passed=bool(b)));assert b,n
check('old_numeric_failure_preserved',json.loads((P/'full_query_acceptance/STATUS.json').read_text())['state']=='STOPPED_NUMERICAL_DIFFERENCE');check('split6_148_full_batch',json.loads((P/'SPLITK6_CPU_RESULT.json').read_text())['status']=='PASS_LIMITED_SPLITK6_FULL_SMALL_BATCH');check('old4_repaired_isolated',json.loads((P/'FFN_REPAIR_V2_RESULT.json').read_text())['new_bit_mismatches']==0)
Arows=0
for branch in ['cond','uncond']:
 ga=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_attention_output.pt'),weights_only=True)[0];gf=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_ffn_input.pt'),weights_only=True)[0]
 for q in sorted((P/'full_query_acceptance').glob(branch+'_*/PASS.json')):
  r=json.loads(q.read_text());begin,end=r['begin'],r['end']
  for n,h in r['files'].items():check(q.parent.name+'_SHA_'+n,sha(q.parent/n)==h)
  for n,g in [('attention_output',ga),('ffn_input',gf)]:
   a=np.load(q.parent/(n+'.npy'));b=g[begin:end].float().numpy();check(q.parent.name+'_'+n,np.array_equal(a.view(np.uint32),b.view(np.uint32)))
  Arows+=end-begin
check('legacy_A_11776_only',Arows==11776)
neg=[]
for name,xx,ww in [('unknown_batch',np.zeros((1,2048),np.float32),np.zeros((768,2048),np.float32)),('FP16_bulk',np.zeros((148,2048),np.float16),np.zeros((768,2048),np.float32)),('FP64_weight',np.zeros((148,2048),np.float32),np.zeros((768,2048),np.float64)),('wrong_K',np.zeros((148,768),np.float32),np.zeros((768,2048),np.float32))]:
 try:expert_linear(xx,ww)
 except (ValueError,TypeError):neg.append(dict(name=name,rejected=True))
 else:raise AssertionError(name)
r=dict(status='PASS_LIMITED_STAGEWISE_PREFLIGHT',check_count=len(checks),checks=checks,reusable_A_rows=Arows,legacy_B_not_reused=True,new_negative_controls=neg,target_GPU_count=0,CUDA_initialized=torch.cuda.is_initialized(),full_layer_pass=False);(P/'STAGEWISE_PREFLIGHT.json').write_text(json.dumps(r,indent=2));print(json.dumps({k:v for k,v in r.items() if k!='checks'}))

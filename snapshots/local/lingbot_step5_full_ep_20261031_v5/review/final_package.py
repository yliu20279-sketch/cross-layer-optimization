import os
os.environ['OMP_NUM_THREADS']='4';os.environ['MKL_NUM_THREADS']='4'
import pathlib,json,hashlib,tarfile,time,sys
R=pathlib.Path(sys.argv[1]);end=time.monotonic()+50000
names=['INDEPENDENT_AUDIT.json','DAG_AUDIT.json','SRAM_INDEPENDENT_AUDIT.json','FEEDBACK_AUDIT.json']
while time.monotonic()<end:
 if all((R/n).exists() for n in names):break
 if (R/'STATUS.json').exists() and json.loads((R/'STATUS.json').read_text())['state'].startswith('STOPPED'):raise RuntimeError('production stopped, failure review retained by original collector')
 time.sleep(5)
else:raise TimeoutError('final pack audit wait expired')
assert all(json.loads((R/n).read_text())['state'].startswith('PASS') for n in names)
if 'full_ep' not in R.name:
 import torch,numpy as np
 torch.set_num_threads(4);G=R.parent/'lingbot_step3_capture_20261028_v1';manifest=json.loads((G/'FIXTURE_MANIFEST.json').read_text());checked=0
 for branch,S in [('cond',49883),('uncond',48986)]:
  rel='fixtures/full_on_s00_'+branch+'_L00_attention_output.pt';q=G/rel
  with q.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
  assert h==next(x['file_sha256'] for x in manifest if x['file']==rel);idx=np.r_[0:32,S-32:S];gold=torch.load(q,weights_only=True)[0,idx].float().numpy()
  for case in [R/'case1',R/'case2']:
   actual=np.load(case/'N15'/(branch+'_attention.npy'));assert np.array_equal(actual.view(np.uint32),gold.view(np.uint32));checked+=actual.size
 (R/'ATTENTION_INDEPENDENT_AUDIT.json').write_text(json.dumps(dict(state='PASS_LIMITED_AUTONOMOUS_SELECTED_ATTENTION_O',elements=checked,bit_mismatches=0,full_KV_prerequisite='previous autonomous full K/V projections, new per-head norm/RoPE',whole_step5=False),indent=2))
critical={'noc_feedback_round1.csv','noc_feedback_round2.csv','domain_service_round1.csv','domain_service_round2.csv'};members=[]
for q in sorted(R.rglob('*')):
 if not q.is_file():continue
 rel=q.relative_to(R)
 if '__pycache__' in rel.parts or q.name.endswith(('.tar.gz','.zip')) or q.name in ['FINAL_REVIEW_MANIFEST.json','FINAL_REVIEW_DELIVERY.json']:continue
 if rel.parts[0]=='run' and not(len(rel.parts)==2 and q.name in critical):continue
 if 'full_ep' in R.name and q.stat().st_size>4*2**20:continue
 if q.stat().st_size>64*2**20:continue
 q.chmod(0o644);members.append(q)
rows=[]
for q in members:
 with q.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
 rows.append(dict(file=str(q.relative_to(R)),bytes=q.stat().st_size,sha256=h))
(R/'FINAL_REVIEW_MANIFEST.json').write_text(json.dumps(rows,indent=2))
with tarfile.open(R/'final_review.tar.gz','w:gz') as t:
 for q in members+[R/'FINAL_REVIEW_MANIFEST.json']:t.add(q,arcname=str(q.relative_to(R)))
with (R/'final_review.tar.gz').open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
(R/'FINAL_REVIEW_DELIVERY.json').write_text(json.dumps(dict(sha256=h,bytes=(R/'final_review.tar.gz').stat().st_size,payloads=len(members),review_only='full_ep' in R.name,whole_step5=False),indent=2));print(h,len(members),flush=True)

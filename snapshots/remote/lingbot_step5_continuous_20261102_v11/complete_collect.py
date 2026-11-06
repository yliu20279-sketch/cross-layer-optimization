import pathlib,json,time,sys,hashlib,tarfile,stat
R=pathlib.Path(sys.argv[1]);end=time.monotonic()+140000;required=['INDEPENDENT_AUDIT.json','DAG_AUDIT.json','SRAM_INDEPENDENT_AUDIT.json','FEEDBACK_AUDIT.json']
while time.monotonic()<end:
 final=(R/'FINAL_REVIEW_DELIVERY.json').exists() or (R/'FINAL_DELIVERY.json').exists()
 if final and (R/'DELIVERY.json').exists() and all((R/n).exists() for n in required):break
 if (R/'STATUS.json').exists() and json.loads((R/'STATUS.json').read_text())['state'].startswith('STOPPED'):raise RuntimeError('production failed, original failure bundle retained')
 time.sleep(5)
else:raise TimeoutError('all final gates wait expired')
assert all(json.loads((R/n).read_text())['state'].startswith('PASS') for n in required)
critical=set(required+['JOIN_BINDING.json','COMPLETE_RAW_MANIFEST.json','COMPLETE_PERMISSION_AUDIT.json']);feedback={'noc_feedback_round1.csv','noc_feedback_round2.csv'}
raw=[];members=[];bad=[]
exclude={'COMPLETE_RAW_MANIFEST.json','COMPLETE_REVIEW_MANIFEST.json','COMPLETE_REVIEW_DELIVERY.json','COMPLETE_PERMISSION_AUDIT.json'}
for q in sorted(R.rglob('*')):
 if q.is_dir():
  if q.stat().st_mode&5!=5:bad.append(str(q))
  continue
 if not q.is_file() or '__pycache__' in q.parts or q.suffix not in ['.npy','.json','.csv','.py','.cpp','.so','.yml','.yaml'] or q.name in exclude:continue
 rel=q.relative_to(R);isrun=rel.parts[0]=='run'
 if isrun and not(len(rel.parts)==2 and q.suffix=='.csv'):continue
 with q.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
 raw.append(dict(file=str(rel),bytes=q.stat().st_size,sha256=h,included_in_compact=q.name in critical or q.name in feedback or (not isrun and q.stat().st_size<4*2**20)))
 if not q.stat().st_mode&4:bad.append(str(q))
 if raw[-1]['included_in_compact']:members.append(q)
for q in [R,*R.parents]:
 if q.stat().st_mode&5!=5:bad.append(str(q))
assert not bad,bad
(R/'COMPLETE_RAW_MANIFEST.json').write_text(json.dumps(dict(scope='numeric arrays, native event/CSV and code snapshot; archives and raw console logs excluded',members=raw),indent=2));(R/'COMPLETE_PERMISSION_AUDIT.json').write_text(json.dumps(dict(POSIX_other_read_traverse=True,cross_account_login=False,checked_payloads=len(raw),bad=[]),indent=2));members.extend([R/'COMPLETE_RAW_MANIFEST.json',R/'COMPLETE_PERMISSION_AUDIT.json'])
manifest=[]
for q in members:
 q.chmod(0o644)
 with q.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
 manifest.append(dict(file=str(q.relative_to(R)),bytes=q.stat().st_size,sha256=h))
(R/'COMPLETE_REVIEW_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
with tarfile.open(R/'complete_review.tar.gz','w:gz') as t:
 for q in members+[R/'COMPLETE_REVIEW_MANIFEST.json']:t.add(q,arcname=str(q.relative_to(R)))
with (R/'complete_review.tar.gz').open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
r=dict(state='COMPLETE_ALL_RECEIPTS_COMPACT_RAW_SHA_INDEX',sha256=h,bytes=(R/'complete_review.tar.gz').stat().st_size,payloads=len(members),raw_index_members=len(raw),full_numeric_arrays_local=False,whole_step5=False);(R/'COMPLETE_REVIEW_DELIVERY.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))

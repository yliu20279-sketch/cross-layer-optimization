import pathlib,json,time,sys,tarfile,hashlib
R=pathlib.Path(__file__).resolve().parent;end=time.monotonic()+140000
while time.monotonic()<end:
 if all((R/n).exists() for n in ['INDEPENDENT_AUDIT.json','DAG_AUDIT.json','SRAM_INDEPENDENT_AUDIT.json','FEEDBACK_AUDIT.json']):break
 if (R/'STATUS.json').exists() and json.loads((R/'STATUS.json').read_text())['state'].startswith('STOPPED'):raise RuntimeError('target stopped, original failure collector preserves trace')
 time.sleep(5)
else:raise TimeoutError('final wait budget')
files=[q for q in sorted(R.rglob('*')) if q.is_file() and 'run' not in q.relative_to(R).parts and '__pycache__' not in q.parts and q.stat().st_size<4*2**20 and not q.name.endswith(('.tar.gz','.zip')) and q.name not in ['FINAL_MANIFEST.json','FINAL_DELIVERY.json']]
manifest=[]
for q in files:
 with q.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
 q.chmod(0o644);manifest.append(dict(file=str(q.relative_to(R)),bytes=q.stat().st_size,sha256=h))
(R/'FINAL_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
with tarfile.open(R/'final_review.tar.gz','w:gz') as t:
 for q in files+[R/'FINAL_MANIFEST.json']:t.add(q,arcname=str(q.relative_to(R)))
with (R/'final_review.tar.gz').open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
(R/'FINAL_DELIVERY.json').write_text(json.dumps(dict(sha256=h,bytes=(R/'final_review.tar.gz').stat().st_size,payloads=len(files),review_only=True,full_arrays_and_raw_traces_on113=True,whole_step5=False),indent=2))

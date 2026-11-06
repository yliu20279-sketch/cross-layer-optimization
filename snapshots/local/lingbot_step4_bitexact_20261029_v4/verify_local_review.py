import pathlib,hashlib,json,tarfile,shutil
p=pathlib.Path('lingbot_step4_bitexact_20261029_v4').resolve();archive=p/'review.tar.gz';expected=(p/'review.tar.gz.sha256').read_text().split()[0]
with archive.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
assert actual==expected
with tarfile.open(archive,'r:gz') as tar:
 for m in tar.getmembers():
  assert not m.name.startswith('/') and '..' not in pathlib.PurePosixPath(m.name).parts and not m.issym() and not m.islnk()
 tar.extractall(p,filter='data')
r=p/'review';manifest=json.loads((r/'REVIEW_MANIFEST.json').read_text());count=0
for row in manifest['files']:
 q=r/row['file'];assert q.stat().st_size==row['bytes']
 with q.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==row['sha256']
 count+=1
for q in r.iterdir():
 if q.is_file() and q.suffix in ['.json','.md','.txt']:shutil.copy2(q,p/q.name)
report=dict(status='PASS_LOCAL_COMPACT_REVIEW_SHA256',payload_files=count,payload_bytes=manifest['bytes'],archive_bytes=archive.stat().st_size,archive_sha256=actual,not_full_remote_payload=True,full_EX2_KV_Golden_tables_remain_on_113=True,whole_step4_complete=False)
(p/'LOCAL_VERIFICATION.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))

import json,hashlib,tarfile,datetime
from pathlib import Path
R=Path(__file__).resolve().parent
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while chunk:=f.read(8*1024*1024):h.update(chunk)
    return h.hexdigest()
files=[]
for p in sorted(R.rglob('*')):
    if not p.is_file() or '__pycache__' in p.parts:continue
    if p.name in ['EVIDENCE.tar.gz','EVIDENCE.sha256','FILE_MANIFEST.json','DELIVERY.json','PIPELINE.log']:continue
    if p.name.endswith('.docker.tar.gz'):continue
    files.append(dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=digest(p)))
(R/'FILE_MANIFEST.json').write_text(json.dumps(files,indent=2))
archive=R/'EVIDENCE.tar.gz'
with tarfile.open(archive,'w:gz',compresslevel=1) as tar:
    tar.add(R/'FILE_MANIFEST.json',arcname='FILE_MANIFEST.json')
    for row in files:tar.add(R/row['path'],arcname=row['path'])
sha=digest(archive)
(R/'EVIDENCE.sha256').write_text(sha+'  EVIDENCE.tar.gz\n')
(R/'DELIVERY.json').write_text(json.dumps(dict(state='REMOTE_PACKAGE_READY',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    archive_bytes=archive.stat().st_size,archive_sha256=sha,payload_files=len(files),payload_bytes=sum(x['bytes'] for x in files)),indent=2))
print(json.dumps(dict(state='REMOTE_PACKAGE_READY',bytes=archive.stat().st_size)))

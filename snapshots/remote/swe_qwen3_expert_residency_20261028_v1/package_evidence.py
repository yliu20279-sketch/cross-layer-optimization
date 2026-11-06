import hashlib,json,tarfile
from pathlib import Path
R=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
rows=[]
for p in sorted(R.rglob('*')):
 if p.is_file() and '__pycache__' not in p.parts and p.name not in ['EVIDENCE.tar.gz','FILE_MANIFEST.json','DELIVERY.json']:
  rows.append(dict(path=p.relative_to(R).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
(R/'FILE_MANIFEST.json').write_text(json.dumps(rows,indent=2))
with tarfile.open(R/'EVIDENCE.tar.gz','w:gz') as t:
 t.add(R/'FILE_MANIFEST.json',arcname='FILE_MANIFEST.json',recursive=False)
 for x in rows:t.add(R/x['path'],arcname=x['path'],recursive=False)
receipt=dict(state='SEALED',archive_bytes=(R/'EVIDENCE.tar.gz').stat().st_size,archive_sha256=sha(R/'EVIDENCE.tar.gz'),payload_files=len(rows),payload_bytes=sum(x['bytes'] for x in rows))
(R/'DELIVERY.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))

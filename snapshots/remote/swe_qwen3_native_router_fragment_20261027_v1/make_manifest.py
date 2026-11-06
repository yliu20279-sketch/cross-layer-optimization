import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent
rows=[]
for p in sorted(R.rglob('*')):
 if p.is_file() and '__pycache__' not in p.parts and p.name!='DELIVERY_MANIFEST.json':
  rows.append(dict(path=p.relative_to(R).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
(R/'DELIVERY_MANIFEST.json').write_text(json.dumps(rows,indent=2))
print(json.dumps(dict(files=len(rows),bytes=sum(x['bytes'] for x in rows))))

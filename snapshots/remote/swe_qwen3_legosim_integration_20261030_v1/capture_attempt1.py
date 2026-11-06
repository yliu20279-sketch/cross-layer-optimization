import hashlib,json,tarfile
from pathlib import Path
P=Path('/mnt/sda1/h3240101068/swe_qwen3_legosim_integration_20261030_v1');R=P/'unified_layers'
members=[]
for p in R.rglob('*'):
 if not p.is_file() or '__pycache__' in p.parts:continue
 rel=p.relative_to(R)
 if p.stat().st_size>40*2**20 or 'quiet_full_phase2' in rel.parts:continue
 members.append(p)
manifest=[]
for p in sorted(members):
 manifest.append(dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
(R/'REVIEW_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
with tarfile.open(P/'UNIFIED_LAYERS_ATTEMPT1_REVIEW.tar.gz','w:gz') as t:
 for p in members+[R/'REVIEW_MANIFEST.json']:t.add(p,arcname='unified_layers/'+str(p.relative_to(R)))
print(len(members),flush=True)

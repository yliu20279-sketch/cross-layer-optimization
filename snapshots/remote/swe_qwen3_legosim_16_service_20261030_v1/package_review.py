import json,hashlib,tarfile
from pathlib import Path
R=Path(__file__).resolve().parent
assert json.loads((R/'INDEPENDENT_AUDIT.json').read_text())['state']=='PASS_LIMITED_16_REAL_GATE_HOST_PCIE_HB_NOC_TWO_ROUND'
members={p for p in R.rglob('*') if p.is_file() and not any(v in p.parts for v in ['source','build','popnet_xy_source','popnet_xy_build','__pycache__']) and p.stat().st_size<40*2**20}
members.update(R/n for n in json.loads((R/'FREEZE.json').read_text()))
members=sorted(members)
manifest=[dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in members]
(R/'MANIFEST.json').write_text(json.dumps(manifest,indent=2));pack=R.parent/'SWE_QWEN3_LEGOSIM_16_SERVICE_REVIEW.tar.gz'
with tarfile.open(pack,'w:gz') as t:
 for p in members+[R/'MANIFEST.json']:t.add(p,arcname=R.name+'/'+str(p.relative_to(R)))
out=dict(state='PASS_LIMITED_16_SERVICE_REVIEW_READY',members=len(members),archive=str(pack),bytes=pack.stat().st_size,sha256=hashlib.sha256(pack.read_bytes()).hexdigest(),audit_version='v2 Path precedence repair only; original failure retained',full_steps_1_7=False)
(R/'DELIVERY_STATUS.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))

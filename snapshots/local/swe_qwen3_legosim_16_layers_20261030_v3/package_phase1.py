import json,hashlib,tarfile,shutil
from pathlib import Path
from check_case import check
R=Path(__file__).resolve().parent;D=R/'case1'
status=check(R,1);(R/'PHASE1_INDEPENDENT_AUDIT.json').write_text(json.dumps(status,indent=2))
members={R/n for n in json.loads((R/'FREEZE.json').read_text())}
members.update(p for p in D.rglob('*') if p.is_file() and p.name not in ['delayInfo.txt','routing_xy.csv','PHASE2_PASS.json'])
members.update(R/n for n in ['PHASE1_INDEPENDENT_AUDIT.json','EARLY_PREFILL_L0_AUDIT.json','README.md'])
for phase in ['prefill','decode']:members.add(R/'data'/(phase+'_gold.bin'))
members.add(R/'run1/clock_round1.csv')
manifest=[dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(members)]
(R/'PHASE1_MANIFEST.json').write_text(json.dumps(manifest,indent=2));pack=R.parent/(R.name+'_PHASE1_REVIEW.tar.gz')
with tarfile.open(pack,'w:gz') as t:
 for p in sorted(members)+[R/'PHASE1_MANIFEST.json']:t.add(p,arcname=R.name+'/'+str(p.relative_to(R)))
receipt=dict(state='PASS_LIMITED_FULL_16_NODE_PHASE1_REVIEW',archive=str(pack),members=len(members),bytes=pack.stat().st_size,sha256=hashlib.sha256(pack.read_bytes()).hexdigest(),full_steps_1_7=False)
(R/'PHASE1_DELIVERY.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))

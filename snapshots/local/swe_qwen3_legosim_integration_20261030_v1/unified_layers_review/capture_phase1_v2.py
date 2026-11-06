import json,hashlib,tarfile,shutil
from pathlib import Path
P=Path('/mnt/sda1/h3240101068/swe_qwen3_legosim_integration_20261030_v1');R=P/'unified_layers_fifo_v2'
assert json.loads((R/'PHASE1_AUDIT.json').read_text())['state']=='PASS_LIMITED_UNIFIED_PHASE1_TWO_LAYER'
shutil.copy2(R/'RUN3.log',R/'PHASE1_RUN_LOG.txt')
members=[p for folder in ['case1','cpu_data'] for p in (R/folder).iterdir() if p.is_file()]
members += [p for p in R.iterdir() if p.is_file() and p.suffix in ['.py','.cpp','.so','.json','.yml','.txt','.log'] and p.name not in ['RUN3.log','REVIEW_MANIFEST.json']]
members += [R/'cpu',R/'run3/bench.txt',R/'run3/proc_r1_p1_t0/cpu.log']
members=sorted(set(members));manifest=[dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in members]
(R/'PHASE1_REVIEW_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
pack=P/'UNIFIED_LAYERS_FIFO_V2_PHASE1.tar.gz'
with tarfile.open(pack,'w:gz') as t:
 for p in members+[R/'PHASE1_REVIEW_MANIFEST.json']:t.add(p,arcname='unified_layers_fifo_v2/'+str(p.relative_to(R)))
print(json.dumps(dict(members=len(members),bytes=pack.stat().st_size,sha256=hashlib.sha256(pack.read_bytes()).hexdigest())))

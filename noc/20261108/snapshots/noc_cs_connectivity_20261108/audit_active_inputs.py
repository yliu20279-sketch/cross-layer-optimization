"""Read-only audit of the running application input snapshots."""
from pathlib import Path
import datetime,hashlib,json
R=Path(__file__).resolve().parent
V=R.parent/'noc_crosslayer_validation_20261108'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(4194304),b''):h.update(block)
    return h.hexdigest()
files={};cases={}
for name in ('mesh_l2','fixed_cs_l1','mesh_l24'):
    p=V/name/'input_hashes.json'
    if not p.exists():continue
    inputs=json.loads(p.read_text());cases[name]=len(inputs)
    for filename,digest in inputs.items():
        assert filename not in files or files[filename]==digest,('snapshot disagreement',filename)
        files[filename]=digest
assert cases
differences=[name for name,digest in files.items() if sha(Path(name))!=digest]
value={'state':'passed' if not differences else 'failed','time':datetime.datetime.now().isoformat(),
       'cases':cases,'unique_inputs_checked':len(files),'changed':differences,
       'scope':'input immutability only; no completed application claim'}
tag=datetime.datetime.now().strftime('%H%M%S')
(R/('active_input_audit_'+tag+'.json')).write_text(json.dumps(value,indent=2))
print(json.dumps(value,indent=2));assert not differences

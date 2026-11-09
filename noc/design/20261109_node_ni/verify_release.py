"""Audit this selected drawing package. No external commands or network access."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parent
names=[
    '.gitignore','README.md','README_v3.md','requirements.txt',
    'draw_node_v2.py','draw_node_v3.py','check_node_v3.py',
    'interface_model_checks.py','node_interface_v3.json',
    'static_checks_v3.json','interface_model_checks.json',
    'figures/05_node_configuration_assignment.png',
    'figures/05_node_configuration_assignment.svg','verify_release.py'
]
allowed=set(names)|{'release_check.json'}
actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
assert set(names)<=actual,sorted(set(names)-actual)
assert actual<=allowed,sorted(actual-allowed)
for name in ['static_checks_v3.json','interface_model_checks.json']:
    assert json.loads((ROOT/name).read_text(encoding='utf-8'))['status']=='PASS'
static=json.loads((ROOT/'static_checks_v3.json').read_text(encoding='utf-8'))
for entry in static['files']:
    assert hashlib.sha256((ROOT/entry['path']).read_bytes()).hexdigest()==entry['sha256'],entry['path']
rows=[{'path':name,'bytes':(ROOT/name).stat().st_size,'sha256':hashlib.sha256((ROOT/name).read_bytes()).hexdigest()} for name in names]
report={'status':'PASS','scope':'selected drawing package and checked source hashes; not RTL verification','third_party_PDFs_or_crops_included':False,'files':rows}
(ROOT/'release_check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
print(f'PASS: {len(rows)} selected files; source/check hashes match; no paper PDFs, datasets, binaries or traces.')

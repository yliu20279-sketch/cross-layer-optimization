import csv
import json
from pathlib import Path
import sys
model=sys.argv[1]
run=Path('runs')/f'{model}_dual01'
base=Path('../ca_p0_1b_dual_migration_20261103_v10')/run
files=sorted(run.glob('request_*.bin'))
assert files
for file in files:
    assert file.read_bytes()==(base/file.name).read_bytes(),file.name
for req in ('request_a','request_b'):
    a=json.loads((run/f'{req}_PHASES.json').read_text())
    b=json.loads((base/f'{req}_PHASES.json').read_text())
    assert len(a)==len(b)
    for x,y in zip(a,b):
        assert len(x['routes'])==len(y['routes'])
        for p,q in zip(x['routes'],y['routes']):
            assert (p['selected'],p['weights'])==(q['selected'],q['weights'])
rows=list(csv.reader((run/'backend/KV_BATCH.csv').open()))
assert rows and len(rows)%4==0
for i in range(0,len(rows),4):
    batch=rows[i:i+4]
    issues=[r for r in batch if r[0]=='issue']
    complete=[r for r in batch if r[0]=='complete']
    assert len(issues)==len(complete)==2
    assert {r[2] for r in issues}=={'1','2'}
    assert {tuple(r[2:]) for r in issues}=={tuple(r[2:]) for r in complete}
    assert [r[0] for r in batch]==['issue','issue','complete','complete']
    assert issues[0][1]==issues[1][1]
print(json.dumps({'status':'PASS_LIMITED_DUAL_MODEL_KV_READ_CONCURRENCY',
                  'binary_members_bitwise':len(files),'route_slots_and_weights_equal':True,
                  'paired_kv_batches':len(rows)//4,'formal_performance':False}))


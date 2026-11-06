import datetime,hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent
frozen=json.loads((R/'FREEZE.json').read_text());checked=[]
for name,digest in frozen['files'].items():
    assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest,name
    checked.append(name)
access=json.loads((R/'PROBLEM_ACCESS.json').read_text())
assert access['utc']>frozen['utc'] and access['gold_column_read'] is False and access['hidden_tests_to_actor'] is False
data=dict(state='PASS_FROZEN_METHOD_UNCHANGED',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),freeze_utc=frozen['utc'],problem_access_utc=access['utc'],files=checked,scope='code/protocol identity and recorded input-column boundary, not task success or numeric certification')
(R/'FROZEN_METHOD_VERIFICATION.json').write_text(json.dumps(data,indent=2));print(json.dumps(dict(state=data['state'],files=len(checked))))

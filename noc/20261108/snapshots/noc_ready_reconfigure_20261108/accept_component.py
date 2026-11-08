"""Reconcile separate retry results without rewriting any failed status."""
from pathlib import Path
import datetime,hashlib,json
R=Path(__file__).resolve().parent;V=R.parent/'noc_crosslayer_validation_20261108'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
test=json.loads((R/'status_retry3.json').read_text())
old=json.loads((R/'original_components_validation.json').read_text())
assert test['state']==old['state']=='passed'
assert len(test['cases'])==4
assert test['binary_sha256']==old['binary_sha256']==sha(R/'noc/build/popnet_cs_ni')
changed=[];count=0
for p in (V/'noc').rglob('*'):
    if not p.is_file() or 'build' in p.parts or p.suffix not in ('.h','.cpp','.cc','.txt'):continue
    rel=p.relative_to(V/'noc');q=R/'noc'/rel
    assert q.is_file(),str(rel)
    count+=1
    if sha(p)!=sha(q):changed.append(str(rel))
assert changed==['adapter/changes/dynamic_control.cpp'],changed
assert (R/'dynamic_control.original.cpp').read_bytes()==(V/'noc/adapter/changes/dynamic_control.cpp').read_bytes()
value={'state':'passed','time':datetime.datetime.now().isoformat(),'composed_protocol_cases':4,
       'original_protocol_cases_rechecked':22,'binary_sha256':test['binary_sha256'],
       'source_files_compared':count,'changed_sources':changed,
       'change_scope':'diagnostic duplicate-ARM probe only; active V untouched',
       'authoritative_results':['status_retry3.json','original_components_validation.json'],
       'historical_failed_build_or_test_statuses_preserved':True,
       'application_or_performance_complete':False}
(R/'accepted_component_validation.json').write_text(json.dumps(value,indent=2));print(json.dumps(value,indent=2))

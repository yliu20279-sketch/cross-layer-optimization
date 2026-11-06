import json,hashlib,shutil,datetime,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;A=R.parent/'swe_qwen3_step3_acceptance_20261027_v1'
gate=json.loads((R/'DEVELOPMENT_GATE.json').read_text());assert gate['state']=='DEVELOPMENT_GATE_PASS'
assert json.loads((R/'BACKEND_EQUIVALENCE.json').read_text())['state']=='PASS_LIMITED_EXACT_OUTPUT'
assert json.loads((R/'IMAGE_VERIFICATION.json').read_text())['state']=='PASS'
for item in json.loads((R/'IMAGE_VERIFICATION.json').read_text())['images']:
    image=('swebench/sweb.eval.x86_64.'+item['instance_id']).replace('__','_1776_').lower()+':latest'
    actual=subprocess.check_output(['docker','image','inspect',image,'--format','{{.Id}}'],text=True).strip()
    assert actual==item['image_id'],'Image tag drift before holdout access'
A.mkdir(exist_ok=False)
names=['backend.py','run_repair.py','policy.py','experiment.py','validation.py','run_acceptance.py','evaluate_acceptance.py',
       'audit_acceptance.py','audit_capture.py','finish_acceptance.py','launch_acceptance.py','PROTOCOL.json','BACKEND_ADAPTATION.json',
       'NEW_HOLDOUT_REGISTRATION.json','IMAGE_VERIFICATION.json','HOLDOUT_IMAGE_ARCHIVES.json','SOURCE_ATTESTATION.json','BASELINE_TESTS.json']
for name in names:shutil.copy2(R/name,A/name)
selected=dict(mode=gate['selected'].removeprefix('development_'),development_gate_sha256=hashlib.sha256((R/'DEVELOPMENT_GATE.json').read_bytes()).hexdigest(),
    source_root=str(R),rule='two official dev resolved, preserve existing tests, no infrastructure failures, then minimum generated tokens',
    evidence='development results are selected, not unbiased success estimates',precision='original BF16',host_GiB=128,HB_GiB=8,NPU_runs=0)
(A/'SELECTED_METHOD.json').write_text(json.dumps(selected,indent=2))
files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(A.iterdir()) if p.is_file()}
(A/'FREEZE.json').write_text(json.dumps(dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),files=files,problem_bodies_read=False,gold_column_read=False,hidden_tests_to_actor=False),indent=2))
print(str(A))

import json,hashlib,datetime,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent
assert not (R/'LAUNCH.json').exists(),'Do not seal or edit a running candidate'
assert json.loads((R/'CONTROLLER_CONTRACT_TEST_V5.json').read_text())['state']=='PASS_CPU_CONTEXT_AND_SEMANTIC_EDIT_GUARD'
assert json.loads((R/'FRAMEWORK_PREFLIGHT.json').read_text())['state']=='PASS_ORIGINAL_FRAMEWORK_ENTRYPOINTS'
PY=R.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
subprocess.run([str(PY),str(R/'test_policy.py')],check=True)
subprocess.run([str(PY),str(R/'test_validation.py')],check=True)
files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(R.iterdir()) if p.is_file() and
       (p.suffix=='.py' or p.name in ['PROTOCOL.json','SOURCE_ATTESTATION.json','NEW_HOLDOUT_REGISTRATION.json','BACKEND_ADAPTATION.json','BASELINE_TESTS.json'])}
(R/'CANDIDATE_READY.json').write_text(json.dumps(dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),files=files,
    state='READY_INDEPENDENT_GPU1_DEVELOPMENT',policy_checks_pass=True,controller_contract_scope='CPU context and semantic invalid-edit guard, model calls0; not SWE admission',
    precision='original BF16',host_GiB=128,HB_GiB=8,NPU_runs=0,new_holdout_bodies_read=False),indent=2))
print('CANDIDATE_READY',len(files))

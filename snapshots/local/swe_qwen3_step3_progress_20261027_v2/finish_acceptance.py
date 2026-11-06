import json,time,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;pid=json.loads((R/'LAUNCH.json').read_text())['pid']
while Path(f'/proc/{pid}').exists():
    if Path(f'/proc/{pid}/stat').read_text().split()[2]=='Z':break
    time.sleep(10)
assert json.loads((R/'STATUS.json').read_text())['state']=='ACCEPTANCE_GENERATION_DONE'
PY=R.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
EPY=R.parent/'swe_qwen3_step3_gpu_20261026_v1/eval_venv/bin/python3.11'
subprocess.run([str(EPY),str(R/'evaluate_acceptance.py')],check=True)
subprocess.run([str(PY),str(R/'audit_acceptance.py')],check=True)
scores=json.loads((R/'OFFICIAL_EVALUATION.json').read_text())
state='STEP3_LIMITED_PILOT_FUNCTIONAL_PASS' if scores['state']=='HOLDOUT_FUNCTIONAL_PASS' else 'STEP3_FUNCTIONAL_ADMISSION_FAILED'
(R/'FINAL_STATUS.json').write_text(json.dumps(dict(state=state,official=scores,precision='original BF16',host_GiB=128,HB_GiB=8,NPU_runs=0,
    scope='selected development and two frozen new holdout pilots, not population rate/target numerical or timing certification'),indent=2))

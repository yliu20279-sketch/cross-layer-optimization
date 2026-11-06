import json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;P=R.parent/'swe_qwen3_step3_progress_20261027_v2'
registration=json.loads((P/'NEW_HOLDOUT_REGISTRATION.json').read_text())['tasks'];results=[]
out=R/'framework_preflight';out.mkdir(exist_ok=False)
for task in registration:
    tid=task['instance_id'];image=('swebench/sweb.eval.x86_64.'+tid).replace('__','_1776_').lower()+':latest'
    assert len(task['base_commit'])==40 and all(c in '0123456789abcdef' for c in task['base_commit'])
    testcommand='/opt/miniconda3/envs/testbed/bin/python '+('tests/runtests.py --help' if task['repo']=='django/django' else '-m pytest --help')
    command='git reset --hard '+task['base_commit']+' && '+testcommand
    with (out/(tid+'.log')).open('w') as f:
        p=subprocess.run(['docker','run','--rm','--network','none','--cpus','2','--memory','4g','--pids-limit','512','--label','swe_qwen3_v4_framework=1','-w','/testbed',image,'bash','-lc',command],stdout=f,stderr=subprocess.STDOUT,timeout=120)
    results.append(dict(instance_id=tid,command=testcommand,returncode=p.returncode))
value=dict(state='PASS_ORIGINAL_FRAMEWORK_ENTRYPOINTS' if all(r['returncode']==0 for r in results) else 'FRAMEWORK_ENTRYPOINT_FAILURE',results=results,
           problem_bodies_read=False,hidden_tests_read=False,gold_read=False,model_generate_calls=0,NPU_runs=0,scope='help/CLI metadata only; no holdout test or repair run')
(R/'FRAMEWORK_PREFLIGHT.json').write_text(json.dumps(value,indent=2));print(json.dumps(value,indent=2))

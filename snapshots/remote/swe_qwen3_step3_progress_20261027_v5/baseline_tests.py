"""Original actor-image existing tests only. No gold or hidden test projection."""
import json,subprocess,traceback,time,datetime
from pathlib import Path
R=Path(__file__).resolve().parent;O=R.parent/'swe_qwen3_step3_gpu_20261026_v1'
tasks=[t for t in json.loads((O/'TASK_REGISTRATION.json').read_text())['tasks'] if t['split']=='dev']
results=[]
for task in tasks:
    tid=task['instance_id'];out=R/'baseline_existing_tests'/tid;out.mkdir(parents=True,exist_ok=False)
    image=('swebench/sweb.eval.x86_64.'+tid).replace('__','_1776_').lower()+':latest'
    cid=subprocess.check_output(['docker','run','-d','--network','none','--cpus','2','--memory','4g','--pids-limit','512',
        '--label','swe_qwen3_v4_baseline=1','-w','/testbed',image,'sleep','15m'],text=True).strip()
    entry=dict(instance_id=tid,container_id=cid,image=image)
    try:
        subprocess.run(['docker','exec',cid,'git','reset','--hard',task['base_commit']],check=True,capture_output=True,timeout=60)
        started=time.monotonic()
        with (out/'test_output.txt').open('w') as f:
            p=subprocess.run(['docker','exec',cid,'/opt/miniconda3/envs/testbed/bin/python','-m','pytest','-q'],stdout=f,stderr=subprocess.STDOUT,timeout=120)
        entry.update(returncode=p.returncode,seconds=time.monotonic()-started,state='PASS_ORIGINAL_EXISTING_TESTS' if p.returncode==0 else 'BASELINE_TEST_FAILURE')
    except Exception:entry.update(state='BASELINE_INFRA_FAILURE',traceback=traceback.format_exc())
    finally:subprocess.run(['docker','stop','--time','2',cid],capture_output=True,timeout=20)
    (out/'RESULT.json').write_text(json.dumps(entry,indent=2));results.append(entry)
report=dict(state='PASS_ORIGINAL_EXISTING_TESTS_BOTH' if all(x['state']=='PASS_ORIGINAL_EXISTING_TESTS' for x in results) else 'BASELINE_NOT_READY',
    utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),results=results,model_generate_calls=0,gold_read=False,hidden_tests_read=False,NPU_runs=0,
    scope='CPU clean original image tests only; no model repair or hidden evaluation success')
(R/'BASELINE_TESTS.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

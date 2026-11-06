import datetime,json,re,subprocess,time
from pathlib import Path
r=Path(__file__).resolve().parent
tasks=json.loads((r.parent/'swe_qwen3_step3_gpu_20261026_v1/development_agent_inputs.json').read_text())
initial={}
for task in tasks:
    p=r/task['instance_id']/'TOOL_EVENTS_GUARD.json'
    initial[task['instance_id']]=len(json.loads(p.read_text())) if p.exists() else 0
(r/'STAGNATION_POLICY.json').write_text(json.dumps(dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),rule='Three new consecutive identical repeated_failed_action_blocked events with identical repository hash after this policy starts; stop only matching own task container, retain partial patch and score; not full-budget solve result',initial_event_counts=initial),indent=2))
for _ in range(1080):
    status=json.loads((r/'STATUS.json').read_text()) if (r/'STATUS.json').exists() else {}
    if status.get('state') in ['GENERATION_FINISHED_EVALUATION_PENDING','FAILED_RETAINED']:break
    for task in tasks:
        out=r/task['instance_id'];p=out/'TOOL_EVENTS_GUARD.json'
        if not p.exists() or (out/'STAGNATION_STOP.json').exists() or (out/'RESULT.json').exists() or (out/'FAILURE.json').exists():continue
        events=json.loads(p.read_text())[initial[task['instance_id']]:]
        if len(events)<3:continue
        tail=events[-3:]
        if not all(x.get('kind')=='repeated_failed_action_blocked' and x.get('command')==tail[0].get('command') and x.get('state_sha256')==tail[0].get('state_sha256') for x in tail):continue
        image=('swebench/sweb.eval.x86_64.'+task['instance_id']).replace('__','_1776_').lower()+':latest'
        ids=re.findall(r'with ID\s+([0-9a-f]{64})',(r/'RUN.log').read_text())
        for cid in ids:
            info=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
            if info['Config']['Image']!=image or not info['State']['Running']:continue
            assert info['Config']['Labels'].get('swe_qwen3_step3_v2')=='1' and info['HostConfig']['NetworkMode']=='none'
            (out/'STAGNATION_STOP.json').write_text(json.dumps(dict(state='CONTROLLED_STAGNATION_STOP',container_id=cid,events=tail,not_full_budget_result=True),indent=2))
            subprocess.run(['docker','stop','--time','2',cid],check=True,capture_output=True,timeout=15)
    time.sleep(5)

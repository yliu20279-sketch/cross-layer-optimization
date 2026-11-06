import datetime,json,re,subprocess,time,types
from pathlib import Path
import run_repair as rr
r=Path(__file__).resolve().parent
task='marshmallow-code__marshmallow-1343';out=r/task
def load(p):
    try:return json.loads(p.read_text())
    except (FileNotFoundError,json.JSONDecodeError):return None
initial=len(load(out/'TOOL_EVENTS.json') or [])
image='swebench/sweb.eval.x86_64.marshmallow-code_1776_marshmallow-1343:latest'
ids=re.findall(r'with ID\s+([0-9a-f]{64})',(r/'RUN.log').read_text())
matches=[]
for cid in ids:
    i=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
    if i['Config']['Image']==image and i['State']['Running']:
        assert i['Config']['Labels'].get('swe_qwen3_step3_v2')=='1' and i['HostConfig']['NetworkMode']=='none';matches.append(cid)
if len(matches)!=1:raise RuntimeError('No unique active own task container')
cid=matches[0]
probe=types.SimpleNamespace(config=types.SimpleNamespace(cwd='/testbed'),container_id=cid)
probe.fingerprint=lambda:rr.LimitedDocker.fingerprint(probe)
state=probe.fingerprint()
(r/'EMPTY_SEARCH_POLICY_V2.json').write_text(json.dumps(dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),initial_actions=initial,state_sha256=state,rule='Only new events after this point: three identical find+grep commands with exit0 and empty output, no repository byte change; diagnostic early stop, not full-budget solve result'),indent=2))
for _ in range(600):
    if (out/'RESULT.json').exists() or (out/'FAILURE.json').exists() or (out/'STAGNATION_STOP.json').exists():break
    events=(load(out/'TOOL_EVENTS.json') or [])[initial:]
    if len(events)>=3:
        tail=events[-3:];command=tail[0].get('command','')
        if command.startswith('find ') and 'grep' in command and all(e.get('command')==command and e.get('result',{}).get('returncode')==0 and e.get('result',{}).get('output','').strip()=='' for e in tail):
            if probe.fingerprint()==state:
                (out/'STAGNATION_STOP.json').write_text(json.dumps(dict(state='CONTROLLED_NO_PROGRESS_STOP',container_id=cid,command=command,new_empty_search_events=3,state_sha256=state,not_full_budget_result=True),indent=2))
                subprocess.run(['docker','stop','--time','2',cid],capture_output=True,check=True,timeout=15);break
    time.sleep(5)
probe.container_id=None

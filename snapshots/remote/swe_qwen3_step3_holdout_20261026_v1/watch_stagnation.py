import json,re,subprocess,time,types
from pathlib import Path
import run_repair as rr
R=Path(__file__).resolve().parent
ids=['astropy__astropy-12907','astropy__astropy-14182'];initial={}
def read(p):
    try:return json.loads(p.read_text())
    except (FileNotFoundError,json.JSONDecodeError):return None
def active(tid):
    image=('swebench/sweb.eval.x86_64.'+tid).replace('__','_1776_').lower()+':latest'
    candidates=re.findall(r'with ID\s+([0-9a-f]{64})',(R/'RUN.log').read_text())
    for cid in candidates:
        info=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
        if info['Config']['Image']==image and info['State']['Running']:
            assert info['Config']['Labels'].get('swe_qwen3_step3_v2')=='1' and info['HostConfig']['NetworkMode']=='none'
            return cid
for _ in range(1320):
    status=read(R/'STATUS.json') or {}
    if status.get('state') in ['GENERATION_FINISHED_EVALUATION_PENDING','FAILED_RETAINED']:break
    for tid in ids:
        d=R/tid
        if not d.exists() or not (d/'BASE_RESET.json').exists() or any((d/x).exists() for x in ['RESULT.json','FAILURE.json','STAGNATION_STOP.json']):continue
        cid=active(tid)
        if not cid:continue
        probe=types.SimpleNamespace(config=types.SimpleNamespace(cwd='/testbed'),container_id=cid)
        if tid not in initial:initial[tid]=rr.LimitedDocker.fingerprint(probe)
        guards=read(d/'TOOL_EVENTS_GUARD.json') or [];events=read(d/'TOOL_EVENTS.json') or []
        reason=None
        if len(guards)>=3:
            tail=guards[-3:]
            if all(x.get('kind')=='repeated_failed_action_blocked' and x.get('command')==tail[0].get('command') and x.get('state_sha256')==tail[0].get('state_sha256') for x in tail):reason='THREE_IDENTICAL_FAILED_ACTION_REJECTIONS'
        if len(events)>=3 and not reason:
            tail=events[-3:];command=tail[0].get('command','')
            if command.startswith('find ') and 'grep' in command and all(e.get('command')==command and e.get('result',{}).get('returncode')==0 and e.get('result',{}).get('output','').strip()=='' for e in tail):
                if rr.LimitedDocker.fingerprint(probe)==initial[tid]:reason='THREE_IDENTICAL_EMPTY_SEARCHES_UNCHANGED_FILES'
        if reason:
            (d/'STAGNATION_STOP.json').write_text(json.dumps(dict(state='CONTROLLED_STAGNATION_STOP',reason=reason,container_id=cid,not_full_budget_result=True),indent=2))
            subprocess.run(['docker','stop','--time','2',cid],capture_output=True,check=True,timeout=15)
    time.sleep(5)

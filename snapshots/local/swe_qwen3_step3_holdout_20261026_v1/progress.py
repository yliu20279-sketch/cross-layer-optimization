import json,time,sys
from pathlib import Path
R=Path(__file__).resolve().parent
def read(p):
    try:return json.loads(p.read_text())
    except (FileNotFoundError,json.JSONDecodeError):return None
s=read(R/'STATUS.json') or {};out=dict(state=s.get('state'),requests=s.get('requests'),completion=(R/'COMPLETION.json').exists(),archive_ready=(R/'EVIDENCE.sha256').exists(),preflight_error=read(R/'PREFLIGHT_FAILURE.json'),finish_error=read(R/'FINISH_FAILURE.json'))
out['last_requests']=[]
for d in sorted((R/'requests').glob('*'))[-2:]:
    q=read(d/'REQUEST.json') or {}
    out['last_requests'].append({k:q.get(k) for k in ['request_id','task_id','prompt_tokens','new_tokens','peak_allocated_bytes']} if q else dict(request=d.name,inflight=True))
out['tasks']={}
for tid in ['astropy__astropy-12907','astropy__astropy-14182']:
    d=R/tid;events=read(d/'TOOL_EVENTS.json') or [];result=read(d/'RESULT.json') or {}
    out['tasks'][tid]=dict(elapsed=round(time.time()-events[0]['start_utc']) if events else None,exit=result.get('agent_result',{}).get('exit_status'),stopped=read(d/'STAGNATION_STOP.json'),failure=(d/'FAILURE.json').exists(),guard_count=len(read(d/'TOOL_EVENTS_GUARD.json') or []),actions=[dict(command=e.get('command'),returncode=e.get('result',{}).get('returncode'),output_chars=len(e.get('result',{}).get('output',''))) for e in events[-2:]])
if '--compact' in sys.argv:
    out=dict(state=out['state'],last=out['last_requests'],tasks={k:{x:v[x] for x in ['elapsed','exit','failure','guard_count']} for k,v in out['tasks'].items()},completion=out['completion'],archive_ready=out['archive_ready'],preflight_error=out['preflight_error'],finish_error=out['finish_error'])
print(json.dumps(out,ensure_ascii=False))

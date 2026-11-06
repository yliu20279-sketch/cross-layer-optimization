import json,time
from pathlib import Path
r=Path(__file__).resolve().parent
def read(p):
    try:return json.loads(p.read_text())
    except (FileNotFoundError,json.JSONDecodeError):return None
out=dict(status=read(r/'STATUS.json'),completion=(r/'AUTHORIZED_COMPLETION.json').exists(),finish_failure=read(r/'FINISH_FAILURE.json'))
out['requests']=[]
for d in sorted((r/'requests').iterdir())[-3:]:
    q=read(d/'REQUEST.json')
    out['requests'].append({k:q.get(k) for k in ['request_id','task_id','prompt_tokens','new_tokens','peak_allocated_bytes']} if q else dict(request=d.name,state='IN_FLIGHT'))
out['tasks']={}
for task in ['marshmallow-code__marshmallow-1359','marshmallow-code__marshmallow-1343']:
    d=r/task;events=read(d/'TOOL_EVENTS.json') or []
    out['tasks'][task]=dict(elapsed_since_first_tool_seconds=round(time.time()-events[0]['start_utc']) if events else None,actions=[dict(command=e.get('command'),returncode=e.get('result',{}).get('returncode'),output_chars=len(e.get('result',{}).get('output',''))) for e in events[-2:]],guard_events=len(read(d/'TOOL_EVENTS_GUARD.json') or []),stagnation_stop=(d/'STAGNATION_STOP.json').exists(),result=(d/'RESULT.json').exists(),failure=(d/'FAILURE.json').exists())
print(json.dumps(out,ensure_ascii=False))

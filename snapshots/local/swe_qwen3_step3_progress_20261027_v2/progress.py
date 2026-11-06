import json
from pathlib import Path
R=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text()) if p.exists() else None
state=read(R/'STATUS.json');result=dict(state=state,gate=read(R/'DEVELOPMENT_GATE.json'),backend_gate=read(R/'BACKEND_EQUIVALENCE.json'))
result['tasks']=[]
for arm in ['development_nonthinking','development_thinking']:
    for p in sorted((R/arm).glob('*')) if (R/arm).exists() else []:
        events=read(p/'EVENTS.json') or []
        reqs=sorted((R/'inference'/arm/p.name/'requests').glob('*/REQUEST.json'))
        last=read(reqs[-1]) if reqs else None
        result['tasks'].append(dict(arm=arm,task=p.name,result=read(p/'RESULT.json'),events=len(events),
            last_action=events[-1] if events else None,requests=len(reqs),
            last_request={k:last[k] for k in ['prompt_tokens','new_tokens','generation_wall_seconds','thinking']} if last else None))
print(json.dumps(result,indent=2))

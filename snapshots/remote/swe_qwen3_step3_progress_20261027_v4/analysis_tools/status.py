import json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def read(p):
    try:return json.loads(p.read_text())
    except (FileNotFoundError,json.JSONDecodeError):return None
state=read(R/'STATUS.json');gate=read(R/'DEVELOPMENT_GATE.json')
summary=dict(state=state,final=read(R/'FINAL_STATUS.json'),pipeline_failure=read(R/'PIPELINE_FAILURE.json'),tasks=[])
if gate:
    summary['official']={k:[dict(instance_id=v['instance_id'],resolved=v['resolved'],admissible=v['admissible']) for v in rows] for k,rows in gate['results'].items()}
for path in sorted((R/'development_thinking').glob('*')) if (R/'development_thinking').exists() else []:
    events=read(path/'EVENTS.json') or [];last=events[-1] if events else {}
    check=last.get('post_edit_validation') or last.get('submission_validation')
    summary['tasks'].append(dict(instance_id=path.name,result=read(path/'RESULT.json'),turns=len(events),last_request=last.get('request'),
        library_state=last.get('library_state'),last_check=dict(syntax=check['syntax']['returncode'],tests=check['tests']['returncode'] if check['tests'] else None) if check else None))
print(json.dumps(summary,indent=2))

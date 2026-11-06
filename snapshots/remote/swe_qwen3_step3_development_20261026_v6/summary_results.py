import json
from pathlib import Path
r=Path(__file__).resolve().parent
def load(p):
    try:return json.loads(p.read_text())
    except (FileNotFoundError,json.JSONDecodeError):return None
reports=load(r/'OFFICIAL_EVALUATION.json') or []
tasks=[]
for report in reports:
    for tid,v in report.items():
        tests=v.get('tests_status',{})
        result=load(r/tid/'RESULT.json') or {}
        stop=load(r/tid/'STAGNATION_STOP.json')
        tasks.append(dict(instance_id=tid,resolved=v['resolved'],exit_status=stop['state'] if stop else result.get('agent_result',{}).get('exit_status'),patch_bytes=(r/tid/'COMPLETE_PATCH.diff').stat().st_size,
            test_counts={key:{k:len(items) for k,items in value.items()} for key,value in tests.items()}))
out=dict(tasks=tasks,requests=len(list((r/'requests').glob('*/REQUEST.json'))),capture_audit=(load(r/'CAPTURE_AUDIT.json') or {}).get('state'),direct_code=load(r/'diagnostic_followup/DIRECT_CODE_CONTRAST.json'),capacity=load(r/'diagnostic_followup/CAPACITY_RESULT.json'),completion=(load(r/'AUTHORIZED_COMPLETION.json') or {}).get('state'),finish_failure=load(r/'FINISH_FAILURE.json'),archive_ready=(r/'EVIDENCE.sha256').exists())
print(json.dumps(out,ensure_ascii=False))

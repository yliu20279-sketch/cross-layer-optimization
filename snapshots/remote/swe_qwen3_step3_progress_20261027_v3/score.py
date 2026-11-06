import json
from pathlib import Path
from evaluate import evaluate
R=Path(__file__).resolve().parent
assert json.loads((R/'STATUS.json').read_text())['state']=='DEVELOPMENT_GENERATION_DONE'
tasks=json.loads((R/'DEVELOPMENT_INPUTS.json').read_text());arm='development_thinking'
scores=evaluate(arm,tasks)
for score,task in zip(scores,tasks):
    result=json.loads((R/arm/task['instance_id']/'RESULT.json').read_text())
    score['library_source_patch']=bool((result.get('library_state') or {}).get('paths'))
    score['admissible']=bool(score.get('admissible')) and score['library_source_patch'] and result['status']!='INFRA_ERROR' and result['patch_collection_returncode']==0
passed=len(scores)==2 and all(s['admissible'] for s in scores)
gate=dict(state='DEVELOPMENT_GATE_PASS' if passed else 'DEVELOPMENT_GATE_FAILED',selected=arm if passed else None,
          results={arm:scores},gold_column_read=False,hidden_tests_to_actor=False,NPU_runs=0)
(R/'DEVELOPMENT_GATE.json').write_text(json.dumps(gate,indent=2));print(gate['state'])

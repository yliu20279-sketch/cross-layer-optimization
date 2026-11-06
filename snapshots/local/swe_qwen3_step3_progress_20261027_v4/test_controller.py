"""Scripted CPU test: failed actual validation returns to the loop, never repairs source itself."""
import json,sys
from pathlib import Path
import backend as b
import experiment as e
R=Path(__file__).resolve().parent
class Scripted:
    def __init__(self):self.index=0
    def generate(self,messages,task,limit,capture):
        actions=[
            "python - <<'PY'\nfrom pathlib import Path\np=Path('src/marshmallow/__init__.py');p.write_text(p.read_text()+'\\ndef controller_marker(\\n')\nPY",
            'echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT',
            "python - <<'PY'\nfrom pathlib import Path\np=Path('src/marshmallow/__init__.py');p.write_text(p.read_text().replace('\\ndef controller_marker(\\n','')+'\\nraise RuntimeError(\"controller_import_probe\")\\n')\nPY",
            'echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT',
            "python - <<'PY'\nfrom pathlib import Path\np=Path('src/marshmallow/__init__.py');p.write_text(p.read_text().replace('\\nraise RuntimeError(\"controller_import_probe\")\\n','')+'\\n# controller marker\\n')\nPY",
            'python -m pytest -q tests/test_marshalling.py',
            'echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT']
        command=actions[self.index];self.index+=1
        return dict(request_id=f'SCRIPTED{self.index}',new_tokens=1,text='<think>scripted fixture</think>\n```bash\n'+command+'\n```')
old=R.parent/'swe_qwen3_step3_gpu_20261026_v1'
task=next(t for t in json.loads((old/'TASK_REGISTRATION.json').read_text())['tasks'] if t['instance_id']=='marshmallow-code__marshmallow-1343')
task=dict(task,problem_statement='Controller syntax/test gating fixture only, not a SWE repair attempt.')
arm='contract_smoke_auto' if '--auto' in sys.argv else 'contract_smoke_final' if '--final' in sys.argv else 'contract_smoke'
result=e.run_task(Scripted(),task,arm=arm)
out=R/arm/task['instance_id'];events=json.loads((out/'EVENTS.json').read_text());messages=json.loads((out/'MESSAGES.json').read_text())
assert events[1]['submission_validation']['syntax']['returncode']!=0 and events[1]['submission_validation']['tests'] is None
assert events[3]['submission_validation']['syntax']['returncode']==0 and events[3]['submission_validation']['tests']['returncode']!=0
assert any('SUBMISSION_REJECTED_SYNTAX' in m['content'] for m in messages)
assert any('SUBMISSION_REJECTED_EXISTING_TESTS' in m['content'] for m in messages)
assert result['status']=='SUBMITTED' and result['submission_validation_passed'] is True
assert events[-1]['submission_validation']['source_unchanged_through_validation'] is True
assert events[-1]['submission_validation']['targets']==['tests/test_marshalling.py']
if '--auto' in sys.argv:
    assert events[0]['post_edit_validation']['syntax']['returncode']!=0
    assert events[2]['post_edit_validation']['tests']['returncode']!=0
    assert events[4]['post_edit_validation']['tests']['returncode']==0
receipt=dict(state='PASS_CPU_SCRIPTED_SUBMISSION_GATES',checks=['syntax failure blocks submission','actual original pytest failure blocks submission',
    'failures returned to scripted next turn','only scripted actor writes repair bytes','successful submission requires real tests and unchanged source'],
    model_generate_calls=0,NPU_runs=0,scope='CPU controller contract only, not Qwen/SWE repair success')
(R/('CONTROLLER_CONTRACT_TEST_AUTO.json' if '--auto' in sys.argv else 'CONTROLLER_CONTRACT_TEST_FINAL.json' if '--final' in sys.argv else 'CONTROLLER_CONTRACT_TEST.json')).write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2))

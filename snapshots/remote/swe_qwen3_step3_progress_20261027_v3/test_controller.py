"""CPU shell contract test with scripted responses; never a model repair success."""
import json,hashlib
from pathlib import Path
import backend as b
import experiment as e
R=Path(__file__).resolve().parent
class ScriptedBackend:
    def __init__(self):self.index=0
    def generate(self,messages,task,limit,capture):
        commands=[
            ['cat src/marshmallow/__init__.py | head -5'],
            ['cat src/marshmallow/__init__.py | head -5'],
            ["printf 'reproduction only\n' > /tmp/controller_repro.txt"],
            ['echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT'],
            ["/opt/miniconda3/envs/testbed/bin/python - <<'PY'\nfrom pathlib import Path\np=Path('src/marshmallow/__init__.py')\np.write_text(p.read_text()+'\\n# controller contract marker\\n')\nPY"],
            ['false',"printf BAD > /tmp/controller_should_not_exist"],
            ['echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT']]
        blocks=commands[self.index];self.index+=1
        return dict(request_id=f'SCRIPTED{self.index}',new_tokens=1,text='<think>scripted contract fixture</think>\n'+'\n'.join('```bash\n'+c+'\n```' for c in blocks))
def main():
    old=R.parent/'swe_qwen3_step3_gpu_20261026_v1'
    task=next(x for x in json.loads((old/'TASK_REGISTRATION.json').read_text())['tasks'] if x['instance_id']=='marshmallow-code__marshmallow-1343')
    task=dict(task,problem_statement='Controller-only scripted contract fixture. No SWE solution supplied.')
    result=e.run_task(ScriptedBackend(),task,arm='contract_smoke',capture=False)
    out=R/'contract_smoke'/task['instance_id'];events=json.loads((out/'EVENTS.json').read_text())
    messages=json.loads((out/'MESSAGES.json').read_text())
    assert result['status']=='SUBMITTED' and result['library_state']['paths']==['src/marshmallow/__init__.py']
    assert events[1]['actions'][0]['cached'] is True
    assert events[2]['unchanged_library_actions']==3
    assert any('NO_LIBRARY_PATCH' in m['content'] for m in messages)
    tools=json.loads((out/'TOOL_EVENTS.json').read_text())
    assert not any('controller_should_not_exist' in t.get('command','') for t in tools)
    assert sum('cat src/marshmallow/__init__.py | head -5'==t.get('command') for t in tools)==1
    receipt=dict(state='PASS_CPU_SCRIPTED_CONTROLLER_CONTRACT',
        checks=['actual repository inventory','cached unchanged inspection not re-executed','tmp reproduction does not count as library progress',
                'submission without library patch rejected','second block skipped after first failure','complete patch collected'],
        model_generate_calls=0,NPU_runs=0,scope='scripted control-flow/shell checks only; not Qwen/SWE success or functional admission')
    (R/'CONTROLLER_CONTRACT_TEST.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()

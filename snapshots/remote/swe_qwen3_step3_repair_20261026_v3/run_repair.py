import json,copy,time,traceback,subprocess
from pathlib import Path
import backend as b
ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'swe_qwen3_step3_gpu_20261026_v1'

def prompt():
    return dict(system_template='You are a software repair agent. Work autonomously using bash commands in the supplied repository. Reply with a brief action description and exactly ONE fenced bash block. Format:\n```bash\nYOUR_SHELL_COMMAND\n```\nRead command results before choosing the next action. On an error, inspect the current file or error and change your approach; do not repeat a failing command unchanged. Preserve existing tests. Do not assume an edit succeeded until checked. Finish only after testing, by issuing echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT alone. No network is available.',
        instance_template='{{task}}\n\nEach command runs in a new shell; persistent file edits remain. Working directory: {{cwd}}. Use bounded file reads and focused tests to keep outputs manageable. If output is clipped, request a narrower range. Return exactly one fenced bash block per reply.')
b.revised_prompt=prompt

class LimitedDocker(b.LoggedDocker):
    def execute(self,action,cwd='',**kwargs):
        result=super().execute(action,cwd,**kwargs)
        if len(result.get('output',''))>12000:
            result=copy.deepcopy(result);raw=result['output'];result['output']=raw[:6000]+f'\n[OUTPUT CLIPPED: original {len(raw)} characters; full raw log retained; request narrower output]\n'+raw[-6000:]
        return result
b.LoggedDocker=LimitedDocker

def audit_messages():
    messages=json.loads((OLD/'requests/R0010/messages.json').read_text())
    obs=[m for m in messages if m['role']=='user']
    assert any('unknown option' in m['content'] and '<returncode>1</returncode>' in m['content'] for m in obs)
    fake=object.__new__(b.LocalModel)
    rendered=fake.format_observation_messages({},[dict(returncode=9,output='SENTINEL_STDOUT',exception_info='SENTINEL_EXCEPTION')])
    assert all(s in rendered[0]['content'] for s in ['SENTINEL_STDOUT','SENTINEL_EXCEPTION','<returncode>9</returncode>'])
    b.save(ROOT/'FEEDBACK_AUDIT.json',dict(state='PASS',old_error_text_present=True,old_error_returncode_present=True,exception_sentinel_visible=True,old_exception_omission_scope='latent adapter defect; not cause of tiny sed errors which were in output',generic_prompt=prompt()))
    return messages

def development(backend):
    results=[];predictions=[]
    for task in json.loads((OLD/'development_agent_inputs.json').read_text()):
        tid=task['instance_id'];out=ROOT/tid;out.mkdir()
        image=('swebench/sweb.eval.x86_64.'+tid).replace('__','_1776_').lower()+':latest'
        env=b.LoggedDocker(out/'TOOL_EVENTS.json',image=image,cwd='/testbed',timeout=120,run_args=['--label','swe_qwen3_step3_v2=1','--network','none','--cpus','2','--memory','4g','--pids-limit','512'],container_timeout='65m')
        try:
            reset=env.execute({'command':'git reset --hard '+task['base_commit']+' && git clean -fd && git rev-parse HEAD'})
            b.save(out/'BASE_RESET.json',reset)
            if reset['returncode'] or reset['output'].strip().splitlines()[-1]!=task['base_commit']:raise RuntimeError('Base identity mismatch')
            agent=b.DefaultAgent(b.LocalModel(backend,tid,1024),env,**prompt(),step_limit=50,cost_limit=0,wall_time_limit_seconds=2700,max_consecutive_format_errors=3,output_path=out/'TRAJECTORY.json')
            result=agent.run('Work in /testbed. Fix this issue and run relevant regression tests. Do not modify existing tests. Use /opt/miniconda3/envs/testbed/bin/python when available.\n\n'+task['problem_statement'])
            diff=env.execute({'command':'git -c core.fileMode=false diff --binary'})
            # Full diff comes from raw log, not the observation clipping view.
            patch=env.records[-1]['result']['output'];(out/'PATCH.diff').write_text(patch)
            entry=dict(instance_id=tid,agent_result=result,container_id=env.container_id,patch_bytes=len(patch.encode()))
            b.save(out/'RESULT.json',entry);results.append(entry)
            predictions.append(dict(instance_id=tid,model_name_or_path='local_Qwen3_30B_A3B_BF16_v2',model_patch=patch))
            (ROOT/'predictions.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in predictions))
        except Exception:
            entry=dict(instance_id=tid,state='FAIL_RETAINED',traceback=traceback.format_exc(),container_id=env.container_id);b.save(out/'FAILURE.json',entry);results.append(entry)
        finally:
            if env.container_id:b.command(['docker','stop','--time','2',env.container_id],timeout=15);env.container_id=None
        b.save(ROOT/'DEVELOPMENT_PROGRESS.json',results)
    return results

def main():
    b.save(ROOT/'STATUS.json',dict(state='LOADING',NPU_runs=0))
    backend=b.Backend();backend.instrument()
    backend.decoding=dict(do_sample=True,temperature=0.7,top_p=0.8,top_k=20)
    b.save(ROOT/'STATUS.json',dict(state='TINY_REPAIR_RUNNING',NPU_runs=0))
    tiny=b.tiny(backend)
    if tiny['state']!='PASS_TINY_AUTONOMOUS_LOOP':
        b.save(ROOT/'STATUS.json',dict(state='TINY_REPAIR_FAILED_RETAINED',NPU_runs=0));return
    b.save(ROOT/'STATUS.json',dict(state='DEVELOPMENT_RUNNING',NPU_runs=0))
    results=development(backend)
    b.save(ROOT/'STATUS.json',dict(state='GENERATION_FINISHED_EVALUATION_PENDING',development=results,requests=len(backend.requests),NPU_runs=0))

if __name__=='__main__':
    try:main()
    except Exception:
        b.save(ROOT/'STATUS.json',dict(state='FAILED_RETAINED',traceback=traceback.format_exc(),NPU_runs=0));raise

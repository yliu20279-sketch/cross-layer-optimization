import json,copy,time,traceback,subprocess
from pathlib import Path
import backend as b
ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'swe_qwen3_step3_gpu_20261026_v1'

def prompt():
    return dict(system_template='You are a software repair agent. Work autonomously using bash commands in the supplied repository. Reply with a brief action description and exactly ONE fenced bash block. Format:\n```bash\nYOUR_SHELL_COMMAND\n```\nRead the implementation and relevant existing tests. Fix implementation source, not existing tests: those are protected. Prefer Python scripts for editing Python code; do not use sed substitutions to edit code expressions. On an error, read the current file and change the approach. Repeating the same failed command on unchanged files is blocked. Use installed test tools; no network or package installation is available. Verify edits and run relevant existing tests before submitting. Finish by issuing echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT alone.',
        instance_template='{{task}}\n\nEach command runs in a new shell; persistent file edits remain. Working directory: {{cwd}}. Use bounded file reads and focused tests to keep outputs manageable. If output is clipped, request a narrower range. Return exactly one fenced bash block per reply.')
b.revised_prompt=prompt

class LimitedDocker(b.LoggedDocker):
    def __init__(self,*args,**kwargs):
        self.failed={};self.protected=None;self.guard_events=[]
        super().__init__(*args,**kwargs)
    def activate_guard(self,base):self.protected=base
    def fingerprint(self):
        script="import pathlib,hashlib,subprocess; p=pathlib.Path.cwd(); h=hashlib.sha256(); q=subprocess.run(['git','ls-files','-z','--cached','--others','--exclude-standard'],capture_output=True) if (p/'.git').exists() and str(p)=='/testbed' else None; names=q.stdout.decode().split('\\0') if q else [str(f.relative_to(p)) for f in p.glob('*.py')]; [(h.update(n.encode()),h.update((p/n).read_bytes() if (p/n).is_file() and not (p/n).is_symlink() else b'')) for n in sorted(set(names)) if n]; print(h.hexdigest())"
        python='/opt/miniconda3/envs/testbed/bin/python' if self.config.cwd=='/testbed' else 'python3'
        result=b.command(['docker','exec','-w',self.config.cwd,self.container_id,python,'-c',script])
        if result['returncode']:raise RuntimeError('State fingerprint failed: '+str(result))
        return result['stdout'].strip()
    def execute(self,action,cwd='',**kwargs):
        command=action.get('command','').strip();state=self.fingerprint()
        if self.failed.get(command)==state:
            result=dict(output='REPEATED_FAILED_ACTION_BLOCKED: this exact command already failed on the same repository files. Inspect the relevant file/error and choose a different approach. No command was executed.',returncode=78,exception_info='RepeatedFailedAction')
            self.guard_events.append(dict(command=command,state_sha256=state,kind='repeated_failed_action_blocked'))
        else:
            result=super().execute(action,cwd,**kwargs)
            if self.protected:
                changed=b.command(['docker','exec',self.container_id,'git','diff','--name-only',self.protected,'--','tests'])['stdout'].splitlines()
                baseline=set(b.command(['docker','exec',self.container_id,'git','ls-tree','-r','--name-only',self.protected,'tests'])['stdout'].splitlines())
                forbidden=sorted(set(changed)&baseline)
                if forbidden:
                    restore=b.command(['docker','exec',self.container_id,'git','checkout',self.protected,'--',*forbidden])
                    if restore['returncode']:raise RuntimeError('Test protection restore failed')
                    self.guard_events.append(dict(command=command,kind='protected_tests_restored',paths=forbidden))
                    result=dict(result,returncode=73,exception_info='ProtectedTestsViolation',output='PROTECTED_TEST_EDIT_REJECTED: edits to existing tests were reverted. Change implementation source instead.\n'+result.get('output',''))
            if result['returncode']!=0:self.failed[command]=self.fingerprint()
        b.save(self.log.with_name(self.log.stem+'_GUARD.json'),self.guard_events)
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
            env.activate_guard(task['base_commit'])
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
    backend=b.Backend()
    prior=json.loads((ROOT.parent/'swe_qwen3_step3_repair_20261026_v4/PREFILL_EQUIVALENCE.json').read_text())
    if not prior['equal_tokens']:raise RuntimeError('Prior chunking gate failed')
    backend.instrument()
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

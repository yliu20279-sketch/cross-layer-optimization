"""Development-only candidate; no new holdout data access in this module."""
import json,time,hashlib,traceback
from pathlib import Path
import backend as b
import run_repair as rr
from policy import SYSTEM,final_answer,actions,package_roots,library_path,inspection,review
R=Path(__file__).resolve().parent;OLD=R.parent/'swe_qwen3_step3_gpu_20261026_v1'

def git(env,*args):
    value=b.command(['docker','exec',env.container_id,'git',*args])
    if value['returncode']:raise RuntimeError(value)
    return value['stdout']

def source_state(env,base,roots):
    paths=set(git(env,'diff','--name-only',base).splitlines())
    new=set(git(env,'ls-files','--others','--exclude-standard').splitlines());paths|=new
    paths=sorted(p for p in paths if library_path(p,roots));h=hashlib.sha256()
    for p in paths:
        h.update(p.encode())
        if p in new:
            content=b.command(['docker','exec',env.container_id,'cat','--',p]);assert content['returncode']==0
            h.update(content['stdout'].encode())
        else:h.update(git(env,'diff','--binary',base,'--',p).encode())
    return dict(paths=paths,sha256=h.hexdigest())

def run_task(backend,task,mode='thinking',arm='development_thinking',capture=False):
    assert mode=='thinking'
    out=R/arm/task['instance_id'];out.mkdir(parents=True,exist_ok=False)
    image=('swebench/sweb.eval.x86_64.'+task['instance_id']).replace('__','_1776_').lower()+':latest'
    env=rr.LimitedDocker(out/'TOOL_EVENTS.json',image=image,cwd='/testbed',timeout=120,
        run_args=['--label','swe_qwen3_progress_v3=1','--network','none','--cpus','2','--memory','4g','--pids-limit','512'],container_timeout='240m')
    backend.thinking=True;backend.call_number=0
    backend.decoding=dict(do_sample=True,temperature=0.6,top_p=0.95,top_k=20)
    events=[];messages=[];start=time.monotonic();tokens=0;unchanged=0;formats=0;status='STEP_LIMIT';cache={};state=None
    try:
        reset=env.execute(dict(command='git reset --hard '+task['base_commit']+' && git clean -fd && git rev-parse HEAD'))
        assert reset['returncode']==0 and reset['output'].strip().splitlines()[-1]==task['base_commit']
        env.activate_guard(task['base_commit']);b.save(out/'BASE_RESET.json',reset)
        tracked=git(env,'ls-files').splitlines();roots=package_roots(tracked)
        if not roots:raise RuntimeError('No package roots; candidate contract requires explicit adaptation before task use')
        sourcefiles=[p for p in tracked if library_path(p,roots)]
        probe=env.execute(dict(command="pwd; /opt/miniconda3/envs/testbed/bin/python -c 'import sys; print(sys.version); print(sys.executable)'"))
        bootstrap=dict(package_roots=roots,library_files_preview=sourcefiles[:100],total_library_files=len(sourcefiles),interpreter=probe)
        b.save(out/'BOOTSTRAP.json',bootstrap)
        messages=[dict(role='system',content=SYSTEM),dict(role='user',content=task['problem_statement']),
                  dict(role='user',content='ACTUAL REPOSITORY INVENTORY (observed, not a proposed solution):\n'+json.dumps(bootstrap))]
        state=source_state(env,task['base_commit'],roots)
        for turn in range(1,33):
            if time.monotonic()-start>5400:status='WALL_LIMIT';break
            if tokens>=32768:status='TOKEN_LIMIT';break
            if turn>1 and (unchanged>=3 or turn%4==1):messages.append(dict(role='user',content=review(turn,unchanged,state['paths'])))
            rec=backend.generate(messages,arm+'/'+task['instance_id'],min(8192,32768-tokens),capture);tokens+=rec['new_tokens']
            entry=dict(turn=turn,request=rec['request_id'],actions=[])
            try:final=final_answer(rec['text']);commands=actions(final);formats=0
            except ValueError as exc:
                formats+=1;entry['format_error']=str(exc);events.append(entry);b.save(out/'EVENTS.json',events)
                messages.append(dict(role='user',content=str(exc)+' Finish reasoning, then return final-answer bash blocks.'))
                if formats>=3:status='FORMAT_STOP';break
                continue
            messages.append(dict(role='assistant',content=final));observations=[]
            for cmd in commands:
                if time.monotonic()-start>5400:status='WALL_LIMIT';break
                if cmd=='echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT':
                    if len(commands)!=1:
                        result=dict(returncode=79,output='Submission must be the sole command; no commands executed.')
                    elif not state['paths']:
                        result=dict(returncode=79,output='NO_LIBRARY_PATCH: source package unchanged. A caller workaround or standalone script is not a repair. Modify the library while preserving issue inputs.')
                    else:status='SUBMITTED';entry['submit']=True;break
                else:
                    before=env.fingerprint();key=(cmd,before)
                    if inspection(cmd) and key in cache:
                        result=dict(returncode=79,output='ALREADY_OBSERVED_UNCHANGED_READ: command not executed. Prior observation: '+cache[key][:1800]+'\nChoose a different implementation inspection or library edit.')
                        entry['actions'].append(dict(command=cmd,cached=True,returncode=79))
                    else:
                        result=env.execute(dict(command=cmd));after=env.fingerprint()
                        if result['returncode']==0 and before==after and inspection(cmd):cache[key]=result.get('output','')
                        entry['actions'].append(dict(command=cmd,cached=False,returncode=result['returncode']))
                output=result.get('output','')
                if len(output)>6000:output=output[:3000]+'\n[CLIPPED: request narrower output]\n'+output[-3000:]
                observations.append(dict(command=cmd,returncode=result['returncode'],exception=result.get('exception_info',''),output=output))
                if result['returncode']!=0:
                    if len(commands)>1:observations.append(dict(note='Later block skipped because earlier block failed.'))
                    break
            updated=source_state(env,task['base_commit'],roots)
            unchanged=unchanged+1 if updated['sha256']==state['sha256'] else 0;state=updated
            entry.update(library_state=state,unchanged_library_actions=unchanged);events.append(entry)
            messages.append(dict(role='user',content=json.dumps(observations)))
            b.save(out/'EVENTS.json',events);b.save(out/'MESSAGES.json',messages)
            if status in ['SUBMITTED','WALL_LIMIT']:break
    except Exception:status='INFRA_ERROR';b.save(out/'FAILURE.json',dict(traceback=traceback.format_exc()))
    finally:
        b.command(['docker','exec',env.container_id,'git','add','--intent-to-add','.'])
        patch=b.command(['docker','exec',env.container_id,'git','diff','--binary',task['base_commit']])
        (out/'COMPLETE_PATCH.diff').write_text(patch['stdout'])
        result=dict(instance_id=task['instance_id'],mode=mode,arm=arm,status=status,container_id=env.container_id,
            wall_seconds=time.monotonic()-start,new_tokens=tokens,turns=len(events),patch_bytes=len(patch['stdout'].encode()),
            patch_collection_returncode=patch['returncode'],capture=capture,library_state=state)
        b.save(out/'RESULT.json',result);b.save(out/'MESSAGES.json',messages)
        b.command(['docker','stop','--time','2',env.container_id],timeout=15);env.container_id=None
    return result

def main():
    import pyarrow.parquet as pq
    previous=R.parent/'swe_qwen3_step3_progress_20261027_v2'
    gate=json.loads((previous/'DEVELOPMENT_GATE.json').read_text());assert gate['state']=='DEVELOPMENT_GATE_FAILED','Do not launch candidate if v2 passed'
    reg=json.loads((OLD/'TASK_REGISTRATION.json').read_text())['tasks'];ids=[t['instance_id'] for t in reg if t['split']=='dev']
    rows=pq.read_table(OLD/'dev.parquet',filters=[('instance_id','in',ids)],columns=['instance_id','repo','base_commit','version','problem_statement']).to_pylist()
    tasks=[next(t for t in rows if t['instance_id']==i) for i in ids];b.save(R/'DEVELOPMENT_INPUTS.json',tasks)
    backend=b.Backend()
    from validate_backend import validate
    validate(backend);results=[]
    for task in tasks:
        b.ROOT=R/'inference'/'development_thinking'/task['instance_id'];b.ROOT.mkdir(parents=True)
        b.save(R/'STATUS.json',dict(state='DEVELOPMENT_RUNNING',task=task['instance_id'],completed=results,NPU_runs=0))
        results.append(run_task(backend,task));b.save(R/'DEVELOPMENT_RESULTS.json',results)
    b.save(R/'STATUS.json',dict(state='DEVELOPMENT_GENERATION_DONE',completed=results,NPU_runs=0))
if __name__=='__main__':
    try:main()
    except Exception:b.save(R/'STATUS.json',dict(state='INFRA_FAILURE',traceback=traceback.format_exc(),NPU_runs=0));raise

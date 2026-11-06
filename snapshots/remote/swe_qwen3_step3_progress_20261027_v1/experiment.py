import datetime,hashlib,json,time,traceback,subprocess,os
from pathlib import Path
import backend as b
import run_repair as rr
from policy import SYSTEM,final_answer,action,reminder
R=Path(__file__).resolve().parent
OLD=R.parent/'swe_qwen3_step3_gpu_20261026_v1'

def run_task(backend,task,mode,arm,capture=False):
    out=R/arm/task['instance_id'];out.mkdir(parents=True,exist_ok=False)
    image=('swebench/sweb.eval.x86_64.'+task['instance_id']).replace('__','_1776_').lower()+':latest'
    env=rr.LimitedDocker(out/'TOOL_EVENTS.json',image=image,cwd='/testbed',timeout=120,
        run_args=['--label','swe_qwen3_progress_v1=1','--network','none','--cpus','2','--memory','4g','--pids-limit','512'],container_timeout='110m')
    backend.thinking=mode=='thinking';backend.call_number=0
    backend.decoding=dict(do_sample=True,temperature=0.6 if backend.thinking else 0.7,top_p=0.95 if backend.thinking else 0.8,top_k=20)
    messages=[dict(role='system',content=SYSTEM),dict(role='user',content=task['problem_statement'])]
    events=[];start=time.monotonic();tokens=0;unchanged=0;formats=0;status='STEP_LIMIT'
    try:
        reset=env.execute({'command':'git reset --hard '+task['base_commit']+' && git clean -fd && git rev-parse HEAD'})
        assert reset['returncode']==0 and reset['output'].strip().splitlines()[-1]==task['base_commit']
        env.activate_guard(task['base_commit']);before=env.fingerprint();b.save(out/'BASE_RESET.json',reset)
        for turn in range(1,33):
            if time.monotonic()-start>5400:status='WALL_LIMIT';break
            if tokens>=16384:status='TOKEN_LIMIT';break
            if turn>1 and (turn%4==1 or unchanged==3):messages.append(dict(role='user',content=reminder(turn,unchanged)))
            rec=backend.generate(messages,arm+'/'+task['instance_id'],min(4096,16384-tokens),capture)
            tokens+=rec['new_tokens'];entry=dict(turn=turn,request=rec['request_id'])
            try:
                final=final_answer(rec['text'],backend.thinking);cmd=action(final);formats=0
            except ValueError as exc:
                messages.append(dict(role='user',content=str(exc)+' Return a completed final answer with exactly one bash block.'))
                entry.update(format_error=str(exc));events.append(entry);b.save(out/'EVENTS.json',events)
                formats+=1
                if formats>=3:status='FORMAT_STOP';break
                continue
            messages.append(dict(role='assistant',content=final))
            if cmd=='echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT':status='SUBMITTED';entry['submit']=True;events.append(entry);break
            result=env.execute(dict(command=cmd));after=env.fingerprint();unchanged=unchanged+1 if after==before else 0;before=after
            observation=f"<returncode>{result['returncode']}</returncode>\n<exception>{result.get('exception_info','')}</exception>\n<output>{result.get('output','')}</output>"
            messages.append(dict(role='user',content=observation));entry.update(command=cmd,returncode=result['returncode'],unchanged=unchanged)
            events.append(entry);b.save(out/'EVENTS.json',events);b.save(out/'MESSAGES.json',messages)
            if unchanged>=8:
                # Recover with an explicit review, bounded by the common token/turn budget.
                messages.append(dict(role='user',content=reminder(turn,unchanged)))
        b.save(out/'MESSAGES.json',messages)
    except Exception:status='INFRA_ERROR';b.save(out/'FAILURE.json',dict(traceback=traceback.format_exc()))
    finally:
        # Snapshot complete tracked/staged/untracked patch; do not repair model output.
        b.command(['docker','exec',env.container_id,'git','add','--intent-to-add','.'])
        patch=b.command(['docker','exec',env.container_id,'git','diff','--binary',task['base_commit']])
        (out/'COMPLETE_PATCH.diff').write_text(patch['stdout'])
        result=dict(instance_id=task['instance_id'],mode=mode,arm=arm,status=status,container_id=env.container_id,
                    wall_seconds=time.monotonic()-start,new_tokens=tokens,turns=len(events),patch_bytes=len(patch['stdout'].encode()),patch_collection_returncode=patch['returncode'],capture=capture)
        b.save(out/'RESULT.json',result)
        b.command(['docker','stop','--time','2',env.container_id],timeout=15);env.container_id=None
    return result

def main():
    import pyarrow.parquet as pq
    registration=json.loads((OLD/'TASK_REGISTRATION.json').read_text())['tasks']
    ids=[x['instance_id'] for x in registration if x['split']=='dev']
    columns=['instance_id','repo','base_commit','problem_statement','version']
    tasks=pq.read_table(OLD/'dev.parquet',filters=[('instance_id','in',ids)],columns=columns).to_pylist()
    assert len(tasks)==2,(ids,len(tasks))
    tasks=sorted(tasks,key=lambda t:ids.index(t['instance_id']));b.save(R/'DEVELOPMENT_INPUTS.json',tasks)
    backend=b.Backend();results=[]
    for mode in ['nonthinking','thinking']:
        arm='development_'+mode
        for i,task in enumerate(tasks):
            # Separate request roots prevent seed-reset collisions, paired seeds per task.
            b.ROOT=R/'inference'/arm/task['instance_id'];b.ROOT.mkdir(parents=True)
            b.save(R/'STATUS.json',dict(state='DEVELOPMENT_RUNNING',mode=mode,task=task['instance_id'],completed=results,NPU_runs=0))
            results.append(run_task(backend,task,mode,arm,False));b.save(R/'DEVELOPMENT_RESULTS.json',results)
    b.save(R/'STATUS.json',dict(state='DEVELOPMENT_GENERATION_DONE',completed=results,NPU_runs=0))

if __name__=='__main__':
    try:main()
    except Exception:b.save(R/'STATUS.json',dict(state='INFRA_FAILURE',traceback=traceback.format_exc(),NPU_runs=0));raise

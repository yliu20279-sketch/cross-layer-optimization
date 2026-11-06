"""Registered development only; hidden evaluation runs in a separate process."""
import json,os,time,traceback
from pathlib import Path
import run_gpu_baseline as b

PARENT=Path(__file__).resolve().parent
b.ROOT=PARENT/'development_run'
b.ROOT.mkdir(exist_ok=False)

def main():
    if json.loads((PARENT/'TINY_RESULT.json').read_text())['state']!='PASS_TINY_AUTONOMOUS_LOOP':
        raise RuntimeError('Tiny autonomous gate has not passed')
    tasks=json.loads((PARENT/'development_agent_inputs.json').read_text())
    backend=b.Backend();backend.instrument()
    predictions=[]
    for task in tasks:
        tid=task['instance_id'];out=b.ROOT/tid;out.mkdir()
        image=('swebench/sweb.eval.x86_64.'+tid).replace('__','_1776_').lower()+':latest'
        env=b.LoggedDocker(out/'TOOL_EVENTS.json',image=image,cwd='/testbed',timeout=120,
            run_args=['--label','swe_qwen3_step3=1','--network','none','--cpus','2','--memory','4g','--pids-limit','512'],container_timeout='65m')
        try:
            reset=env.execute({'command':'git reset --hard '+task['base_commit']+' && git clean -fd'})
            b.save(out/'BASE_RESET.json',reset)
            if reset['returncode']:raise RuntimeError('Cannot prepare registered base in new task container')
            check=env.execute({'command':'git rev-parse HEAD'})
            if check['returncode'] or check['output'].strip()!=task['base_commit']:raise RuntimeError('Image base commit mismatch')
            config=b.yaml.safe_load((b.MINI/'src/minisweagent/config/default.yaml').read_text())['agent']
            config.update(step_limit=50,cost_limit=0,wall_time_limit_seconds=2700,max_consecutive_format_errors=3,output_path=out/'TRAJECTORY.json')
            agent=b.DefaultAgent(b.LocalModel(backend,tid,1024),env,**config)
            start=time.monotonic()
            result=agent.run('Work in /testbed. Fix the following issue. Inspect the repository and run relevant tests. Do not modify tests. Use /opt/miniconda3/envs/testbed/bin/python where available. Submit when finished.\n\n'+task['problem_statement'])
            diff=env.execute({'command':'git -c core.fileMode=false diff --binary'})
            (out/'PATCH.diff').write_text(diff['output'])
            b.save(out/'RESULT.json',dict(agent_result=result,wall_seconds=time.monotonic()-start,container_id=env.container_id,base_commit=task['base_commit'],scope='autonomous development trajectory; official evaluator decides resolution'))
            predictions.append(dict(instance_id=tid,model_name_or_path='local_Qwen3_30B_A3B_BF16',model_patch=diff['output']))
            (b.ROOT/'predictions.jsonl').write_text(''.join(json.dumps(p)+'\n' for p in predictions))
        except Exception:
            b.save(out/'FAILURE.json',dict(traceback=traceback.format_exc(),container_id=env.container_id))
        finally:
            if env.container_id:
                b.command(['docker','stop','--time','2',env.container_id],timeout=15);env.container_id=None
    b.save(b.ROOT/'STATUS.json',dict(state='GENERATION_FINISHED_EVALUATION_PENDING',predictions=len(predictions),requests=len(backend.requests),NPU_runs=0))

if __name__=='__main__':
    try:main()
    except Exception:
        b.save(b.ROOT/'STATUS.json',dict(state='FAILED_RETAINED',traceback=traceback.format_exc()));raise

import json
from pathlib import Path
import backend as b
r=Path(__file__).resolve().parent
tasks=json.loads((r/'TASK_REGISTRATION.json').read_text())['tasks'];results=[]
for task in [x for x in tasks if x['split']=='dev']:
    image=('swebench/sweb.eval.x86_64.'+task['instance_id']).replace('__','_1776_').lower()+':latest'
    env=b.DockerEnvironment(image=image,cwd='/testbed',timeout=30,run_args=['--label','swe_qwen3_env_audit=1','--network','none','--cpus','1','--memory','1g','--pids-limit','256'],container_timeout='10m')
    try:
        env.execute(dict(command='git reset --hard '+task['base_commit']))
        default=env.execute(dict(command='python -c "import sys; print(sys.executable); import marshmallow; print(marshmallow.__file__)"'))
        explicit=env.execute(dict(command='/opt/miniconda3/envs/testbed/bin/python -c "import sys; print(sys.executable); import marshmallow; print(marshmallow.__file__)"'))
        results.append(dict(instance_id=task['instance_id'],default_python=default,explicit_testbed_python=explicit,container_id=env.container_id))
    finally:b.command(['docker','stop','--time','2',env.container_id]);env.container_id=None
(r/'ACTOR_ENVIRONMENT_AUDIT.json').write_text(json.dumps(dict(results=results,CUDA_initialized=b.torch.cuda.is_initialized()),indent=2))

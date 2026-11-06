import json
from pathlib import Path
import run_repair as rr
import backend as b
r=Path(__file__).resolve().parent/'guard_regression';r.mkdir()
env=rr.LimitedDocker(r/'TOOL_EVENTS.json',image='swebench/sweb.eval.x86_64.marshmallow-code_1776_marshmallow-1359:latest',cwd='/testbed',timeout=30,run_args=['--label','swe_qwen3_guard_regression=1','--network','none','--cpus','1','--memory','1g','--pids-limit','256'],container_timeout='10m')
try:
    base='b40a0f4e33823e6d0f341f7e8684e359a99060d1'
    assert env.execute(dict(command='git reset --hard '+base))['returncode']==0
    env.activate_guard(base)
    first=env.execute(dict(command='false'));second=env.execute(dict(command='false'))
    assert first['returncode']==1 and second['returncode']==78
    masked_command='/opt/miniconda3/envs/testbed/bin/python -c "raise RuntimeError(123)" || true'
    masked_first=env.execute(dict(command=masked_command));masked_second=env.execute(dict(command=masked_command))
    assert masked_first['returncode']==0 and 'ERROR_OUTPUT_WITH_ZERO_EXIT' in masked_first['output'] and masked_second['returncode']==78
    edit=env.execute(dict(command="printf '\n# deliberate guard regression\n' >> tests/test_deserialization.py"))
    assert edit['returncode']==73
    diff=env.execute(dict(command='git diff --name-only '+base+' -- tests'))
    assert diff['output'].strip()==''
    b.save(r/'RESULT.json',dict(state='PASS',same_failed_action_blocked=True,masked_traceback_repeat_blocked=True,original_zero_exit_preserved=True,existing_test_edit_restored=True,test_diff_empty=True,CUDA_initialized=b.torch.cuda.is_initialized(),container_id=env.container_id))
finally:
    b.command(['docker','stop','--time','2',env.container_id]);env.container_id=None

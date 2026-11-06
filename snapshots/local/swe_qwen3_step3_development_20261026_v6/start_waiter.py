import subprocess,json
from pathlib import Path
r=Path(__file__).resolve().parent
with (r/'WAIT.log').open('xb') as log:
    p=subprocess.Popen([str(r.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'),'-u',str(r/'wait_then_launch.py')],stdout=log,stderr=subprocess.STDOUT,cwd=r,start_new_session=True)
(r/'WAITER.json').write_text(json.dumps(dict(pid=p.pid),indent=2));print(p.pid)

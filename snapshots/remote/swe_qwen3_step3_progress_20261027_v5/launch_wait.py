import json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent
assert not (R/'WAIT_LAUNCH.json').exists()
with (R/'WAIT.log').open('xb') as f:p=subprocess.Popen([str(R.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'),str(R/'wait_previous.py')],cwd=R,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
(R/'WAIT_LAUNCH.json').write_text(json.dumps(dict(pid=p.pid)))
print(p.pid)

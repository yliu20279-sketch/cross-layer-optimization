import subprocess,json
from pathlib import Path
R=Path(__file__).resolve().parent
with (R/'PREFLIGHT.log').open('xb') as f:
    p=subprocess.Popen([str(R.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'),'-u',str(R/'load_and_start.py')],cwd=R,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
(R/'PREFLIGHT_LAUNCH.json').write_text(json.dumps(dict(pid=p.pid)))

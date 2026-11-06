import subprocess,json
from pathlib import Path
r=Path(__file__).resolve().parent
with (r/'FINISH.log').open('xb') as log:
    p=subprocess.Popen([str(r.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'),'-u',str(r/'finish_authorized.py')],cwd=r,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
(r/'FINISH_LAUNCH.json').write_text(json.dumps(dict(pid=p.pid)))

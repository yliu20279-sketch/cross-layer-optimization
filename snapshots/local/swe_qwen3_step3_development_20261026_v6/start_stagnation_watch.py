from pathlib import Path
import subprocess,json
r=Path(__file__).resolve().parent
with (r/'STAGNATION_WATCH.log').open('xb') as log:
    p=subprocess.Popen([str(r.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'),'-u',str(r/'stagnation_watch.py')],stdout=log,stderr=subprocess.STDOUT,start_new_session=True,cwd=r)
(r/'STAGNATION_WATCH_LAUNCH.json').write_text(json.dumps(dict(pid=p.pid)))

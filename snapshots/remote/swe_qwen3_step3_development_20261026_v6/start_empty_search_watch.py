import subprocess,json
from pathlib import Path
r=Path(__file__).resolve().parent
with (r/'EMPTY_SEARCH_WATCH.log').open('xb') as log:
    p=subprocess.Popen([str(r.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'),'-u',str(r/'empty_search_watch.py')],cwd=r,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
(r/'EMPTY_SEARCH_WATCH_LAUNCH.json').write_text(json.dumps(dict(pid=p.pid)))

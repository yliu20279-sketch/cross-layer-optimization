import subprocess,json,os,signal
from pathlib import Path
r=Path(__file__).resolve().parent
pid=json.loads((r/'EMPTY_SEARCH_WATCH_LAUNCH.json').read_text())['pid'];p=Path('/proc')/str(pid)
if p.exists():
    assert p.stat().st_uid==os.getuid() and str(r/'empty_search_watch.py').encode() in (p/'cmdline').read_bytes().split(b'\0')
    os.kill(pid,signal.SIGTERM)
with (r/'EMPTY_SEARCH_WATCH_V2.log').open('xb') as log:
    child=subprocess.Popen([str(r.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'),'-u',str(r/'empty_search_watch.py')],cwd=r,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
(r/'EMPTY_SEARCH_WATCH_V2_LAUNCH.json').write_text(json.dumps(dict(pid=child.pid,previous_watcher_pid=pid,reason='Use a read-only fingerprint carrier without DockerEnvironment cleanup destructor')))

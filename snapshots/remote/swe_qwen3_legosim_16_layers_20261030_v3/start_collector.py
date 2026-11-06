import subprocess,json,time,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;p=R/'COLLECTOR_PID.json'
assert not p.exists(),'collector already registered'
with (R/'COLLECTOR.log').open('w') as f:
 child=subprocess.Popen(['/usr/bin/python3',str(R/'collect_independent.py')],stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True,cwd=R)
p.write_text(json.dumps(dict(pid=child.pid,started_epoch=time.time(),script_sha256=hashlib.sha256((R/'collect_independent.py').read_bytes()).hexdigest(),scope='read/audit/archive only; no numerical rerun'),indent=2));print(child.pid)

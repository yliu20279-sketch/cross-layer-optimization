import subprocess,json
from pathlib import Path
R=Path(__file__).resolve().parent
with (R/'safe_collect.log').open('w') as f:p=subprocess.Popen(['/usr/bin/python3',str(R/'safe_collect.py')],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
(R/'SAFE_COLLECTOR_PID.json').write_text(json.dumps(dict(pid=p.pid,reason='dereference shared immutable math/oracle links in review archive; retain all clock CSV payloads; no target implementation changes')));print(p.pid)

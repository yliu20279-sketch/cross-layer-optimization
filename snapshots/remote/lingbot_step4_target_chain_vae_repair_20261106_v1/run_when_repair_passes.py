import time,json,subprocess,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;S=R.parent/'lingbot_cpu_vae_repair_20261105_v1';py=R.parent/'lingbot_steps1_2_20261027_v1/venv/bin/python'
started=time.monotonic();audit=S/'FULL_CPU_FRAME_attempt2_AUDIT.json'
while not audit.exists():
 assert time.monotonic()-started<1800,'CPU repair prerequisite timeout'
 time.sleep(5)
a=json.loads(audit.read_text());assert a['state']=='PASS_BITWISE' and a['different_elements']==0
for f in json.loads((R/'COMPAT_FREEZE.json').read_text())['files']:
 p=R/'compat'/f['file'];assert hashlib.file_digest(p.open('rb'),'sha256').hexdigest()==f['sha256']
(R/'REPAIR_PREREQUISITE.json').write_text(json.dumps(dict(audit_path=str(audit),audit=a),indent=2))
print('CPU repair passed; launching bounded target chain',flush=True)
subprocess.run([str(py),str(R/'run.py')],check=True,timeout=3700)
subprocess.run([str(py),str(R/'audit.py')],check=True,timeout=120)
print('target acceptance saved',flush=True)

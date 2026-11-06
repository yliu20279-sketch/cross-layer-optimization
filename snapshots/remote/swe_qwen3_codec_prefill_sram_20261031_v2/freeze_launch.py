import json,hashlib,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent
old=json.loads((R/'FREEZE.json').read_text());(R/'BUILD_FREEZE.json').write_text(json.dumps(old,indent=2))
names=list(old)+['run.py','freeze_launch.py']
(R/'FREEZE.json').write_text(json.dumps({n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in names},indent=2))
cfg=json.loads((R/'unified.yml').read_text());ext=[R.parent/'swe_qwen3_legosim_clock_fix_20261030_v1/build/interchiplet']
ext += [Path(p['cmd']) for p in cfg['phase1'] if Path(p['cmd']).is_file()]
ext += [Path(v) for p in cfg['phase2'] for v in p['args'] if v.startswith('/') and Path(v).is_file()]
(R/'EXTERNAL_DEPENDENCIES.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in ext},indent=2))
with (R/'LAUNCH.log').open('w') as f:
 p=subprocess.Popen(['/usr/bin/python3',str(R/'run.py')],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
(R/'LAUNCH_PID.json').write_text(json.dumps(dict(pid=p.pid)))
print('BOUNDED_UNIFIED_STARTED',p.pid)

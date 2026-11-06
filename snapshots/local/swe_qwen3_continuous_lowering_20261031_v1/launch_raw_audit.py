import subprocess,json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent
with (R/'RAW_ORACLE_AUDIT.log').open('w') as f:p=subprocess.Popen(['/usr/bin/python3',str(R/'audit_raw_when_ready.py')],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
(R/'SUPPLEMENTAL_STRICT_GATE.json').write_text(json.dumps(dict(pid=p.pid,script_sha256=hashlib.sha256((R/'audit_raw_when_ready.py').read_bytes()).hexdigest(),state='ADDITIONAL_STRICT_AUDIT_REQUIRED',reason='final BF16 can hide FP32 differences; compare every raw matrix against unchanged CPU C source',original_thresholds_unchanged=True,scope='tightens evidence; does not change frozen target execution or outputs'),indent=2));print(p.pid)

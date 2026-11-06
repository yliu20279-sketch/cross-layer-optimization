import json,hashlib,shutil
from pathlib import Path
R=Path(__file__).resolve().parent;assert not (R/'RUN_PID.json').exists()
assert json.loads((R/'QUEUE_STATUS.json').read_text())['state']=='WAITING_V5_STRICT_FINAL_PASS'
assert json.loads((R/'LIFETIME_CONTROL_AUDIT_V2.json').read_text())['state']=='PASS_LIMITED_TWO_LAYER_CPU_LIFETIME_REUSE'
H=R/'auditor_history';H.mkdir(exist_ok=True)
for name in ['FREEZE.json','WORKER_FREEZE.json','ADDITIONAL_AUDITOR_FREEZE.json']:shutil.copy2(R/name,H/('before_barrier_checksum_'+name))
f=json.loads((R/'FREEZE.json').read_text());f.pop('WORKER_FREEZE.json',None)
for name in ['audit_control.py','LIFETIME_CONTROL_AUDIT_V2.json']:f[name]=hashlib.sha256((R/name).read_bytes()).hexdigest()
(R/'WORKER_FREEZE.json').write_text(json.dumps(f,indent=2));f['WORKER_FREEZE.json']=hashlib.sha256((R/'WORKER_FREEZE.json').read_bytes()).hexdigest();(R/'FREEZE.json').write_text(json.dumps(f,indent=2))
f=json.loads((R/'ADDITIONAL_AUDITOR_FREEZE.json').read_text());f['audit_control.py']=hashlib.sha256((R/'audit_control.py').read_bytes()).hexdigest();(R/'ADDITIONAL_AUDITOR_FREEZE.json').write_text(json.dumps(f,indent=2))
(R/'AUDITOR_AMENDMENT.json').write_text(json.dumps(dict(reason='bind all CPU26 reclamation descriptor bytes to independently reconstructed service output SHA, in addition to CPU24/25',workload_source_changed=False,native_not_started=True,previous_snapshots=str(H)),indent=2));print('AUDITOR_FREEZE_REFRESHED_NO_NATIVE_RESTART')

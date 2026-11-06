import hashlib,json,subprocess,shutil
from pathlib import Path
R=Path(__file__).resolve().parent
freeze=json.loads((R/'FREEZE.json').read_text())
assert all(hashlib.sha256((R/k).read_bytes()).hexdigest()==v for k,v in freeze['files'].items())
audits=[]
# Reuse frozen request auditor in each per-task inference root and perturbation root.
for root in [R,*sorted((R/'inference'/'acceptance').glob('*'))]:
    script=root/'request_auditor.py'
    shutil.copy2(R/'audit_capture.py',script)
    subprocess.run([str(R.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'),str(script)],check=True)
    value=json.loads((root/'CAPTURE_AUDIT.json').read_text());assert value['state']=='PASS_STRUCTURE_HASH_AND_PHASE'
    audits.append(dict(root=str(root.relative_to(R)),audit=value))
(R/'CAPTURE_AUDIT_ALL.json').write_text(json.dumps(dict(state='PASS_STRUCTURE_HASH_AND_PHASE',audits=audits),indent=2))
(R/'FROZEN_METHOD_VERIFICATION.json').write_text(json.dumps(dict(state='PASS',files=len(freeze['files'])),indent=2))

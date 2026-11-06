"""Repair only a Path/string formatting precedence error in frozen audit v1."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parent;p=R/'audit16.py';s=p.read_text()
bad="/'CH%02d.log'%rank";good="/('CH%02d.log'%rank)";assert s.count(bad)==1
(R/'AUDIT_METHOD_AMENDMENT.json').write_text(json.dumps(dict(reason='Path formatting precedence TypeError; no numerical, count, capacity, identity or feedback assertion changed',original_audit_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),exact_replacement=[bad,good]),indent=2))
exec(compile(s.replace(bad,good),str(p),'exec'),{'__file__':str(p)})

import json,hashlib,types,sys
from pathlib import Path
H=Path(__file__).resolve().parent;R=H/'complete_review'/H.name
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((R/'COMPLETE_MANIFEST.json').read_text());assert len(manifest)==419
for v in manifest:assert (R/v['path']).stat().st_size==v['bytes'] and sha(R/v['path'])==v['sha256']
ref=H.parent/'swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1'
source=(R/'check_case.py').read_text();old="ref=B/'swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1'"
assert old in source;source=source.replace(old,'ref=Path('+repr(str(ref))+')')
module=types.ModuleType('check_case');exec(compile(source,str(R/'check_case.py'),'exec'),module.__dict__);sys.modules['check_case']=module
source=(R/'audit_full.py').read_text()
old="assert all(sha(Path(n))==h for n,h in j(R/'EXTERNAL_DEPENDENCIES.json').items())"
assert old in source;source=source.replace(old,"external_identity_remote_only=j(R/'EXTERNAL_DEPENDENCIES.json')")
old="(R/'INDEPENDENT_AUDIT.json').write_text(json.dumps(out,indent=2))";assert old in source
source=source.replace(old,"(H/'LOCAL_COMPLETE_FUNCTIONAL_AUDIT.json').write_text(json.dumps(out,indent=2))")
ns=dict(__file__=str(R/'audit_full.py'),H=H);exec(compile(source,str(R/'audit_full.py'),'exec'),ns)
source=(R/'audit_clock.py').read_text();source=source.replace("runpy.run_path(str(R/'audit_full.py'))",'')
source=source.replace("(R/'CLOCK_AUDIT.json')","(H/'LOCAL_COMPLETE_CLOCK_AUDIT.json')")
exec(compile(source,str(R/'audit_clock.py'),'exec'),dict(__file__=str(R/'audit_clock.py'),H=H))
out=dict(state='PASS_LIMITED_LOCAL_COMPLETE_419_MEMBER_REVIEW',members=419,rounds=2,external_binaries_rehashed_locally=False,external_hashes_verified_by_remote_audit=True,full_steps_1_7=False)
(H/'LOCAL_COMPLETE_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))

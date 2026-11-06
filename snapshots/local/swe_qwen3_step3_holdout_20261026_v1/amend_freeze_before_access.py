import json,shutil,subprocess,sys
from pathlib import Path
r=Path(__file__).resolve().parent
assert not (r/'PROBLEM_ACCESS.json').exists() and not (r/'agent_inputs').exists() and not (r/'LAUNCH.json').exists()
assert not (r/'FREEZE_before_base_check.json').exists()
shutil.move(r/'FREEZE.json',r/'FREEZE_before_base_check.json')
(r/'PRE_ACCESS_AMENDMENT.json').write_text(json.dumps(dict(reason='Watch state fingerprint only after BASE_RESET.json exists, so image initial HEAD cannot define the empty-search baseline',problem_body_read=False,model_or_prompt_or_decoding_changed=False),indent=2))
subprocess.run([sys.executable,str(r/'freeze_method.py')],check=True)

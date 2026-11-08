"""Repeat the original 22 protocol checks on the diagnostic-probe fix only."""
from pathlib import Path
import hashlib,json,shutil,sys
R=Path(__file__).resolve().parent
W=R.parent/'noc_current_control_validation_20261108'
OUT=R/'original_component_regression';OUT.mkdir(exist_ok=False)
shutil.copytree(W/'inputs',OUT/'inputs')
shutil.copy2(R/'noc/build/popnet_cs_ni',OUT/'popnet_cs_ni')
sys.argv=[str(OUT/'run_checks.py')]
namespace={'__file__':str(OUT/'run_checks.py'),'__name__':'__main__'}
exec(compile((W/'run_checks.py').read_text(),str(W/'run_checks.py'),'exec'),namespace)
assert json.loads((OUT/'status.json').read_text())['state']=='passed'
# Changes are limited to the named diagnostic-probe implementation, not
# hardware routing, buffering, serialized control protocol, or active V inputs.
v={'state':'passed','original_protocol_cases':22,'changed_source':'dynamic_control.cpp: test probe only',
   'binary_sha256':hashlib.sha256((OUT/'popnet_cs_ni').read_bytes()).hexdigest()}
(R/'original_components_validation.json').write_text(json.dumps(v,indent=2));print(json.dumps(v))

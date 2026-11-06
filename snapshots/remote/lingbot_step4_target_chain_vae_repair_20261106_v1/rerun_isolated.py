from pathlib import Path
import shutil,sys,subprocess,json
R=Path(__file__).resolve().parent;D=Path(sys.argv[1]).resolve();assert D.parent==R.parent and not D.exists(), 'supply a new sibling isolation directory'
assert json.loads((R/'REPAIR_PREREQUISITE.json').read_text())['audit']['state']=='PASS_BITWISE'
D.mkdir()
for n in ['actor.py','cpu_service.py','gateway.cpp','gateway','libpeer.so','config.yml','phase2.py','run.py','noc_v3_6.gv','ram.csv','audit.py','COMPAT_FREEZE.json','REFERENCE_BINDING.json','PROTOCOL.json','run_when_repair_passes.py']:
 p=D/n;shutil.copy2(R/n,p)
 if p.suffix in ['.py','.cpp','.yml','.json']:p.write_text(p.read_text().replace(str(R),str(D)))
shutil.copytree(R/'compat',D/'compat',ignore=shutil.ignore_patterns('__pycache__'))
py=R.parent/'lingbot_steps1_2_20261027_v1/venv/bin/python';subprocess.run([str(py),str(D/'run_when_repair_passes.py')],check=True,timeout=5600)

"""Isolated rebuild; only diagnostic probe changes, never active V inputs."""
from pathlib import Path
import datetime,hashlib,json,shutil,subprocess
R=Path(__file__).resolve().parent
V=R.parent/'noc_crosslayer_validation_20261108'
state={'state':'building','active_application_sources_modified':False}
def save():
    state['updated']=datetime.datetime.now().isoformat()
    (R/'probe_build_status.json').write_text(json.dumps(state,indent=2))
def run(label,argv):
    with (R/(label+'.log')).open('xb') as f:subprocess.run(argv,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=1200)
save()
try:
    shutil.copytree(V/'noc',R/'noc',ignore=shutil.ignore_patterns('build','__pycache__'))
    original=R/'noc/adapter/changes/dynamic_control.cpp'
    shutil.copy2(original,R/'dynamic_control.original.cpp')
    shutil.copy2(R/'dynamic_control.cpp',original)
    run('configure',['cmake','-S',str(R/'noc'),'-B',str(R/'noc/build'),'-DCMAKE_BUILD_TYPE=Release'])
    run('compile',['cmake','--build',str(R/'noc/build'),'-j','2'])
    state.update(state='passed',binary_sha256=hashlib.sha256((R/'noc/build/popnet_cs_ni').read_bytes()).hexdigest())
    save()
    run('probe_retry2',['python3',str(R/'run_checks.py'),'--attempt','retry2','--probe-fixed'])
except BaseException as e:
    state.update(state='failed',reason=repr(e));save();raise
finally:save()

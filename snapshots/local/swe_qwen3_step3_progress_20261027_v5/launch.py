import json,os,hashlib,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent
assert not (R/'LAUNCH.json').exists(),'Candidate already launched'
ready=json.loads((R/'CANDIDATE_READY.json').read_text())
for name,digest in ready['files'].items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest,name
assert json.loads((R/'CONTROLLER_CONTRACT_TEST_V5.json').read_text())['state']=='PASS_CPU_CONTEXT_AND_SEMANTIC_EDIT_GUARD'
assert json.loads((R/'BASELINE_TESTS.json').read_text())['state']=='PASS_ORIGINAL_EXISTING_TESTS_BOTH'
env=dict(os.environ,CUDA_VISIBLE_DEVICES='1',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True',PYTHONUNBUFFERED='1')
PY=R.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
(R/'METHOD_SNAPSHOT.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in R.iterdir() if p.is_file() and p.suffix in ['.py','.json']},indent=2))
with (R/'RUN.log').open('xb') as f:p=subprocess.Popen([str(PY),str(R/'experiment.py')],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
(R/'LAUNCH.json').write_text(json.dumps(dict(pid=p.pid)))
with (R/'FINISH.log').open('xb') as f:subprocess.Popen([str(PY),str(R/'finish_development.py')],cwd=R,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
subprocess.run([str(PY),str(R/'launch_pipeline.py')],check=True)
print(p.pid)

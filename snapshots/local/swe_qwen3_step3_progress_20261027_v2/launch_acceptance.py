import json,hashlib,subprocess,os
from pathlib import Path
R=Path(__file__).resolve().parent;freeze=json.loads((R/'FREEZE.json').read_text())
for name,digest in freeze['files'].items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest
env=dict(os.environ,CUDA_VISIBLE_DEVICES='0',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True',PYTHONUNBUFFERED='1')
PY=R.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
with (R/'RUN.log').open('xb') as f:p=subprocess.Popen([str(PY),str(R/'run_acceptance.py')],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
(R/'LAUNCH.json').write_text(json.dumps(dict(pid=p.pid)))
with (R/'FINISH.log').open('xb') as f:subprocess.Popen([str(PY),str(R/'finish_acceptance.py')],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
print(p.pid)

import hashlib,json,os,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;PY=R.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
frozen=json.loads((R/'FREEZE.json').read_text())
for name,digest in frozen['files'].items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest
env=dict(os.environ,CUDA_VISIBLE_DEVICES='0',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True',PYTHONUNBUFFERED='1')
with (R/'RUN.log').open('xb') as f:p=subprocess.Popen([str(PY),'-u',str(R/'run_holdout.py')],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
(R/'LAUNCH.json').write_text(json.dumps(dict(pid=p.pid)))
for script,log in [('watch_stagnation.py','WATCH.log'),('finish_holdout.py','FINISH.log')]:
    with (R/log).open('xb') as f:subprocess.Popen([str(PY),'-u',str(R/script)],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
print(p.pid)

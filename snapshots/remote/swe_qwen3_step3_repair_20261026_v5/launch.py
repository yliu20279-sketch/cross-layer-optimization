import subprocess,os,json
from pathlib import Path
r=Path(__file__).resolve().parent
env=dict(os.environ,CUDA_VISIBLE_DEVICES='0',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',PYTHONUNBUFFERED='1',PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True')
python=r.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
with (r/'RUN.log').open('xb') as log:
    p=subprocess.Popen([str(python),'-u',str(r/'run_repair.py')],cwd=r,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
(r/'LAUNCH.json').write_text(json.dumps(dict(pid=p.pid,script=str(r/'run_repair.py'),GPU=0),indent=2))
print(p.pid)

import subprocess
from pathlib import Path
R=Path(__file__).resolve().parent
with (R/'FINISH.log').open('xb') as f:
    p=subprocess.Popen([str(R.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'),str(R/'finish_development.py')],cwd=R,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
print(p.pid)

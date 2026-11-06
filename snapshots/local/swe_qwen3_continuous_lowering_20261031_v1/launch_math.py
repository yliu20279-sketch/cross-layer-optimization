import subprocess,json
from pathlib import Path
R=Path(__file__).resolve().parent;PY=R.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
with (R/'MATH_BUILD.log').open('w') as f:p=subprocess.Popen(['/usr/bin/timeout','900',str(PY),str(R/'build_math.py')],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
(R/'MATH_PID.json').write_text(json.dumps(dict(pid=p.pid,bound_seconds=900)));print(p.pid)

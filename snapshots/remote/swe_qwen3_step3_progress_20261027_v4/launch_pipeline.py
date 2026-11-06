import subprocess,json
from pathlib import Path
R=Path(__file__).resolve().parent
assert not (R/'PIPELINE_LAUNCH.json').exists(),'Pipeline already launched'
with (R/'PIPELINE.log').open('xb') as f:p=subprocess.Popen([str(R.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'),str(R/'pipeline.py')],cwd=R,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
(R/'PIPELINE_LAUNCH.json').write_text(json.dumps(dict(pid=p.pid)))
print(p.pid)

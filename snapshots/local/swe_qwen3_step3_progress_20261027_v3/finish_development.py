import json,time,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;pid=json.loads((R/'LAUNCH.json').read_text())['pid']
while Path(f'/proc/{pid}').exists():
    if Path(f'/proc/{pid}/stat').read_text().split()[2]=='Z':break
    time.sleep(10)
assert json.loads((R/'STATUS.json').read_text())['state']=='DEVELOPMENT_GENERATION_DONE'
EPY=R.parent/'swe_qwen3_step3_gpu_20261026_v1/eval_venv/bin/python3.11'
subprocess.run([str(EPY),str(R/'score.py')],check=True)

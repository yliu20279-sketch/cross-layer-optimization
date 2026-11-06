import json,subprocess,time,os,traceback
from pathlib import Path
R=Path(__file__).resolve().parent
pid=json.loads((R/'LAUNCH.json').read_text())['pid']
while Path('/proc/'+str(pid)).exists():
    stat=Path('/proc/'+str(pid)+'/stat').read_text().split()
    if stat[2]=='Z':break
    time.sleep(10)
state=json.loads((R/'STATUS.json').read_text())
if state['state']!='DEVELOPMENT_GENERATION_DONE':raise RuntimeError(state)
py=R.parent/'swe_qwen3_step3_gpu_20261026_v1/eval_venv/bin/python3.11'
subprocess.run([str(py),str(R/'evaluate.py')],cwd=R,check=True)

import json,time,subprocess
from pathlib import Path
r=Path(__file__).resolve().parent
prior=r.parent/'swe_qwen3_step3_repair_20261026_v5'
pid=json.loads((prior/'LAUNCH.json').read_text())['pid']
for _ in range(300):
    proc=Path('/proc')/str(pid)
    if not proc.exists():break
    assert str(prior/'run_repair.py').encode() in (proc/'cmdline').read_bytes().split(b'\0')
    time.sleep(5)
else:raise RuntimeError('Prior run has not exited; not competing for GPU')
status=json.loads((prior/'STATUS.json').read_text())
if status['state']!='TINY_REPAIR_FAILED_RETAINED':raise RuntimeError('Prior run did not stop at failed tiny gate; review before next launch')
subprocess.run([str(r.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'),str(r/'launch.py')],check=True)

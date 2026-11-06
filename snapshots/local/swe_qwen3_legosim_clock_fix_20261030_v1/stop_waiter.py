import os,signal
from pathlib import Path
pid=1425209;R=Path('/mnt/sda1/h3240101068/swe_qwen3_legosim_16_layers_20261030_v3')
assert not (R/'RUN.log').exists()
p=Path('/proc/%d/cmdline'%pid)
if p.exists():
 assert b'swe_qwen3_legosim_16_layers_20261030_v3/run_full.py' in p.read_bytes();os.kill(pid,signal.SIGTERM);print('stopped prerequisite waiter only')

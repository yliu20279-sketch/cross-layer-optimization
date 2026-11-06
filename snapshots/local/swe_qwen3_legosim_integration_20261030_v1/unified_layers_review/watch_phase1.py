import time,subprocess
from pathlib import Path
P=Path('/mnt/sda1/h3240101068/swe_qwen3_legosim_integration_20261030_v1')
end=time.monotonic()+240
while not (P/'unified_layers_fifo_v2/cpu_data/CPU_PASS.json').exists() and time.monotonic()<end:time.sleep(5)
raise SystemExit(subprocess.call(['python3',str(P/'phase1_audit.py')]))

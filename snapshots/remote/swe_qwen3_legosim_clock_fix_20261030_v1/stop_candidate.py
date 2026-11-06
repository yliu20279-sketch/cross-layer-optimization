import os,signal,json
from pathlib import Path
pid=1298426
P=Path('/mnt/sda1/h3240101068/swe_qwen3_legosim_16_layers_20261030_v2')
proc=Path('/proc/%d/cmdline'%pid)
if proc.exists():
 assert b'swe_qwen3_legosim_16_layers_20261030_v2/unified_full.yml' in proc.read_bytes()
 assert os.getpgid(pid)==pid
 (P/'STOP_REASON.json').write_text(json.dumps(dict(reason='CPU global2.5GHz ticks were treated as1ns with clock_rate1; stop timing candidate and retain functional outputs'),indent=2))
 os.killpg(pid,signal.SIGTERM)
 print('stopped own candidate process group',pid)
else:print('candidate already exited; no process stopped')

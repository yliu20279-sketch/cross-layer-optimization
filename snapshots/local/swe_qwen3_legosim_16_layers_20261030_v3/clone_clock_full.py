import shutil,json,hashlib
from pathlib import Path
B=Path('/mnt/sda1/h3240101068');A=B/'swe_qwen3_legosim_16_layers_20261030_v2';C=B/'swe_qwen3_legosim_clock_fix_20261030_v1';R=B/'swe_qwen3_legosim_16_layers_20261030_v3';R.mkdir(exist_ok=True)
skip={'FREEZE.json','WORKER_FREEZE.json','prepare_config.py','run_full.py','audit_clock.py'}
for p in A.iterdir():
 if not p.is_file() or p.name.startswith(('RUN','AUDIT','STOP','EARLY')) or p.name in skip:continue
 shutil.copy2(p,R/p.name)
shutil.copytree(A/'data',R/'data');shutil.copy2(C/'BINDING.json',R/'CLOCK_BINDING.json')
(R/'CLOCK_AMENDMENT.json').write_text(json.dumps(dict(source=str(A),CPU_clock_rate=2.5,DRAM_service_scale=1.25,controller=str(C/'build/interchiplet'),controller_sha256=hashlib.sha256((C/'build/interchiplet').read_bytes()).hexdigest(),previous_numerics_retained_but_timing_not_promoted=True),indent=2))

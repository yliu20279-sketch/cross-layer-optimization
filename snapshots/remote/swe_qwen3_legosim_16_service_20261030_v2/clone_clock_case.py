import shutil,json,hashlib
from pathlib import Path
B=Path('/mnt/sda1/h3240101068');A=B/'swe_qwen3_legosim_16_service_20261030_v1';C=B/'swe_qwen3_legosim_clock_fix_20261030_v1';R=B/'swe_qwen3_legosim_16_service_20261030_v2';R.mkdir(exist_ok=True)
skip={'FREEZE.json','MANIFEST.json','DELIVERY_STATUS.json','INDEPENDENT_AUDIT.json','prepare_config.py','run_after_pass.py','audit16_clock.py','CONTROLLER_BUILD.json'}
for p in A.iterdir():
 if not p.is_file() or p.name.startswith(('RUN','AUDIT','PREREQUISITE')) or p.name in skip:continue
 shutil.copy2(p,R/p.name)
shutil.copytree(A/'data',R/'data');p=R/'data/plan.txt';p.write_text(p.read_text().replace(str(A),str(R)))
for folder in ['build','popnet_xy_build','popnet_xy_source']:(R/folder).mkdir(exist_ok=True)
shutil.copy2(C/'build/interchiplet',R/'build/interchiplet');shutil.copy2(C/'interchiplet.cpp',R/'interchiplet.cpp');shutil.copy2(C/'domain_service.h',R/'domain_service.h')
shutil.copy2(C/'source/interchiplet/srcs/cmd_handler.cpp',R/'clock_cmd_handler.cpp');shutil.copy2(C/'BINDING.json',R/'CLOCK_BINDING.json')
for p in ['popnet_xy_build/popnet','popnet_xy_source/sim_router.cc']:shutil.copy2(A/p,R/p)
(R/'REUSE_BINDING.json').write_text(json.dumps(dict(original=str(A),numeric_payloads_unchanged=True,CPU_clock_rate=2.5,DRAM_cycle_scale=1.25,controller=str(C/'build/interchiplet'),controller_sha256=hashlib.sha256((R/'build/interchiplet').read_bytes()).hexdigest(),prior_timing_not_certified=True),indent=2))

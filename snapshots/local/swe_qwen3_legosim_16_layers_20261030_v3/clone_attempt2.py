import shutil,json,hashlib
from pathlib import Path
B=Path('/mnt/sda1/h3240101068');A=B/'swe_qwen3_legosim_16_layers_20261030_v1';R=B/'swe_qwen3_legosim_16_layers_20261030_v2';R.mkdir(exist_ok=True)
for p in A.iterdir():
 if not p.is_file() or p.name.startswith(('RUN','AUDIT')) or p.name in ['FREEZE.json','prepare_config.py']:continue
 shutil.copy2(p,R/p.name)
shutil.copytree(A/'data',R/'data')
(R/'REUSE_BINDING.json').write_text(json.dumps(dict(source=str(A),reason='v1 stopped before data computation due to missing WORKER_FREEZE.json; same compiled host/gateway/libfull reused, new worker manifest and isolated result directory',binary_sha256={n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in ['host','gateway','libfull.so']},v1_failure_retained=True),indent=2))

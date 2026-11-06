import json,shutil,os
from pathlib import Path
R=Path(__file__).resolve().parent;P=R/'endpoint_positive';N=R/'endpoint_negative';N.mkdir(exist_ok=False)
for name in ['host','gateway','libfull.so','endpoint_probe.py','noc_v3_6.gv']:shutil.copy2(P/name,N/name)
for name in ['data','EXP16_ALL_FP32.bin','SILU_ALL_BF16.bin']:os.symlink(str(P/name),str(N/name))
# Resolve host output ../case against this directory, not a data symlink.
(N/'data').unlink();shutil.copytree(P/'data',N/'data',symlinks=True)
(N/'probe.yml').write_text((P/'probe.yml').read_text().replace(str(P),str(N)))
(N/'NEGATIVE_PROTOCOL.json').write_text(json.dumps(dict(expected='CPU rejects final acknowledgement with live pinned allocation; no CPU_TEARDOWN_PASS or ENDPOINT_ROOT_PASS',native_scope='single active root/HB endpoint smoke only'),indent=2))

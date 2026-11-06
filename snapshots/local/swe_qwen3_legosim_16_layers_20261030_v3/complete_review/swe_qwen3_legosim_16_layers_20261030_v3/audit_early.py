import json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/'case1';REF=R.parent/'swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1'
files=[v for v in json.loads((REF/'FILES.json').read_text()) if v['phase']=='prefill' and v['layer']==0]
assert len(files)==14
out=[]
for v in files:
 p=D/v['path'];assert p.read_bytes()==(REF/v['path']).read_bytes();out.append(dict(path=v['path'],bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
record=dict(state='PASS_LIMITED_NEW_16NPU_HOST_PCIE_PREFILL_LAYER0_14_STAGES',files=out,scope='new full-service run actual data; CPU-source exact; layer1/decode, PopNet and round2 still pending',full_steps_1_7=False)
(R/'EARLY_PREFILL_L0_AUDIT.json').write_text(json.dumps(record,indent=2));print(record['state'])

"""Read-only independent comparison of functional control replay, not native timing."""
import json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/'control_replay_v2'
F=R.parent/'swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
g=[json.loads(s) for s in (D/'IMMEDIATE_FP32_GATES.jsonl').read_text().splitlines()]
assert len(g)==759 and all(x['exact'] and x['actual_sha256']==x['expected_sha256'] for x in g)
oracle=json.loads((R/'oracle_cpu/RAW_MATRIX_ORACLE.json').read_text())
assert len(oracle)==759
for actual,expected in zip(g,oracle):
 assert actual['actual_sha256']==expected['output_sha256']
 assert all(actual[k]==expected[k] for k in ['M','N','K'])
assert sum(x['M']*x['N'] for x in g)==1626944
files=sorted(D.glob('*.bin'));assert len(files)==56,len(files)
stage=[]
for p in files:
 q=F/p.name;assert q.is_file(),str(q)
 assert p.stat().st_size==q.stat().st_size and sha(p)==sha(q),p.name
 stage.append(dict(name=p.name,bytes=p.stat().st_size,sha256=sha(p)))
checks=json.loads((D/'CHECKS.json').read_text());strict=[c for c in checks if c.get('strict')]
assert len(strict)==12 and all(c['exact'] and c['different']==0 for c in strict)
assert json.loads((D/'LAYOUT_GAPS.json').read_text())==[]
s=json.loads((D/'REPLAY_SUMMARY.json').read_text());assert s['target_native_runs']==0 and s['GPU_runs']==0 and s['layout_gaps']==0
source=json.loads((R/'ALIAS_METHOD.json').read_text());assert sha(R/'base_adapter.py')==source['base_adapter_sha256']
cpu=json.loads((D/'CPU_SERVICES.json').read_text())
out=dict(state='PASS_LIMITED_CPU_CONTROL_ALIAS_REPLAY',FP32_gates_exact=759,FP32_elements=1626944,original_stage_files_exact=56,strict_layer_KV_checks=12,layout_gaps=0,stage_bindings=stage,source_binding=source,target_native_runs=0,GPU_runs=0,full_target_timing=False,full_steps_1_7=False,limits=['in-memory HB control backend; no native timing proof','cached readback aliases retain immutable node; dynamic reclamation not certified','first replay failed on missing positional constant test-backend adapter and remains preserved'])
(R/'ALIAS_REPLAY_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps({k:v for k,v in out.items() if k not in ['stage_bindings','source_binding']}))

from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parent;B=R.parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
for n,h in json.loads((R/'FREEZE.json').read_text()).items():assert sha(R/n)==h
binding=json.loads((R/'attempt1/PRE_RUN_BINDING.json').read_text())
for p,item in binding.items():assert Path(p).stat().st_size==item['bytes'] and sha(p)==item['sha256']
route=B/'swe_qwen3_softmax_top8_20261027_v1';rm={x['path']:x for x in json.loads((route/'FILE_MANIFEST.json').read_text())}
for n in ['attempt1/real_logits_BF16.bin','attempt1/libroute.so','attempt1/gold_IDs.bin','attempt1/gold_weights_BF16.bin','roi_attempt1/METRICS.json','attempt1/RESULTS.json','route_adapter.py','FINAL_STATUS.json']:
 assert sha(route/n)==rm[n]['sha256']
host=B/'swe_qwen3_host_boundary_20261027_v1';hm={x['path']:x for x in json.loads((host/'FILE_MANIFEST.json').read_text())}
assert sha(host/'boundary_service_v2.py')==hm['boundary_service_v2.py']['sha256']
old=json.loads((B/'swe_qwen3_native_router_fragment_20261027_v1/attempt2/PRE_RUN_BINDING.json').read_text())
for p,item in old['files'].items():assert sha(p)==item['sha256']
report=dict(state='PASS_FROZEN_GATE_SOURCE_AND_PARENT_INPUT_IDENTITIES',gate_frozen_files=3,pre_run_bound_files=len(binding),parent_route_members_verified=8,old_native_bound_files=len(old['files']),scope='byte identities; not extra numerical or physical execution certification')
(R/'SOURCE_VERIFICATION.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))

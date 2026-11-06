"""Read-only prefix and frozen-candidate audit; never promotes a running case."""
import json,hashlib,time
from pathlib import Path
R=Path(__file__).resolve().parent;V=R.parent/'swe_qwen3_continuous_portable_20261101_v7'
def j(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for root in [R,V]:
 for name,h in j(root/'FREEZE.json').items():assert sha(root/name)==h,(root.name,name)
assert not (R/'RUN_PID.json').exists(),'candidate already started; pending audit scope no longer applies'
assert j(R/'QUEUE_STATUS.json')['state']=='WAITING_V7_STRICT_FINAL_PASS'
cfg=j(R/'unified_full.yml');baseline=j(V/'unified_full.yml')
assert len(cfg['phase1'])==34 and len(cfg['phase2'])==1
assert cfg==json.loads(json.dumps(baseline).replace(str(V),str(R)))
ram=[t for t in cfg['phase1'] if t['cmd'].endswith('/ramulator2')];assert len(ram)==16
for rank,t in enumerate(ram):
 assert list(map(int,t['args'][:2]))==[rank%4,8+rank//4]
 assert t['args'][2]=='1.25' and t['args'][5]=='536870912'
assert cfg['phase1'][0]['clock_rate']==2.5 and 'LD_BIND_NOW=1' in cfg['phase1'][0]['args']
assert not (R/'data').is_symlink(),'host ../case output must remain in this candidate'
for name in ['shards.txt','parameters.txt','prefill_input.bin','decode_input.bin','prefill_gold.bin','decode_gold.bin']:
 assert sha(R/'data'/name)==sha(V/'data'/name),name
oracle=j(V/'oracle_cpu/RAW_MATRIX_ORACLE.json');rows=[]
p=V/'case1/IMMEDIATE_FP32_GATES.jsonl'
for line in p.read_bytes().splitlines(keepends=True):
 if not line.endswith(b'\n'):break
 rows.append(json.loads(line))
assert 0<len(rows)<=len(oracle)==759
for i,(a,b) in enumerate(zip(rows,oracle)):
 assert a['sequence']==i+1 and a['exact']
 assert a['actual_sha256']==a['expected_sha256']==b['output_sha256']
 assert all(a[k]==b[k] for k in ['M','N','K'])
assert j(R/'OWNED_CONTROL_AUDIT.json')['state']=='PASS_LIMITED_CPU_TWO_LAYER_KV_OWNERSHIP'
assert j(R/'ENDPOINT_AUDIT.json')['leaked_owner_refused']
out=dict(state='PASS_PREFIX_AND_FROZEN_CANDIDATE_ONLY',observed_epoch=time.time(),baseline_round=1,independent_exact_FP32_prefix=len(rows),expected_complete_matrices_per_round=759,candidate_phase1_components=34,candidate_HB_partitions=len(ram),HB_total_bytes=16*536870912,host_GiB=128,precision='original BF16',input_and_golden_identity=True,native_candidate_started=False,GPU_differences='retained',full_steps_1_7=False)
(R/'PENDING_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))

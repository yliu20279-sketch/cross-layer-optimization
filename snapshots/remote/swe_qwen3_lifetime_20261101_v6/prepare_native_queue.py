import json,hashlib,subprocess,shutil,time
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent;V5=B/'swe_qwen3_continuous_cache_20261101_v5'
assert json.loads((R/'LIFETIME_CONTROL_AUDIT.json').read_text())['state']=='PASS_LIMITED_TWO_LAYER_CPU_LIFETIME_REUSE'
assert not (R/'NATIVE_QUEUE_READY.json').exists()
for n in ['audit_cache_stream.py','snapshot_cpu_stats.py','collect_stream.py','watch_cache_live.py']:shutil.copy2(V5/n,R/n)
p=R/'worker.py';s=p.read_text().replace('from integrated_adapter import FullAdapter,UnifiedKV','from lifetime_adapter import FullAdapter,UnifiedKV').replace('   sy=layers[i]','   a.layer_barrier(phase,i)\n   sy=layers[i]');p.write_text(s)
p=R/'check_case.py';s=p.read_text();needle="  if i:assert nodes[i-1]['offset']+nodes[i-1]['bytes']<=n['offset']";assert needle in s
s=s.replace(needle,"  assert n['retired_at']>=n['last_consumer_barrier_start']>=max([n['ready']]+[v['done'] for v in n['readers']])");p.write_text(s)
cfg=(R/'unified_full.yml').read_text().replace(str(V5),str(R));(R/'unified_full.yml').write_text(cfg)
cmd=[x.replace(str(V5),str(R)) for x in json.loads((R/'CPU_BUILD_COMMAND.json').read_text())];(R/'CPU_BUILD_COMMAND.json').write_text(json.dumps(cmd,indent=2));subprocess.run(cmd,check=True)
py=B/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
with (R/'NATIVE_CPU_CONTROLS.log').open('w') as f:subprocess.run([str(py),str(R/'cpu_negative_controls.py')],stdout=f,stderr=subprocess.STDOUT,check=True,timeout=60)
p=R/'collect_stream.py';s=p.read_text();needle=" rounds=[validate(R,i) for i in [1,2]]";assert needle in s
s=s.replace(needle,needle+"\n for i in [1,2]:\n  with (R/('native_lifetime_round%d.log'%i)).open('w') as f:c=subprocess.run(['python3',str(R/'audit_control.py'),'case%d'%i],stdout=f,stderr=subprocess.STDOUT,timeout=600)\n  assert c.returncode==0,('native lifetime audit',i)\n")
s=s.replace('dynamic_reclamation=False','dynamic_reclamation=True');p.write_text(s)
names=list(json.loads((V5/'FREEZE.json').read_text()));names=[n for n in names if n!='WORKER_FREEZE.json']+['lifetime_allocator.h','lifetime_adapter.py','LIFETIME_PLAN.json','LIFETIME_PROTOCOL.json','audit_control.py','LIFETIME_CONTROL_AUDIT.json','ALLOCATOR_CONTROLS.json']
hashes={n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in names};(R/'WORKER_FREEZE.json').write_text(json.dumps(hashes,indent=2));hashes['WORKER_FREEZE.json']=hashlib.sha256((R/'WORKER_FREEZE.json').read_bytes()).hexdigest();(R/'FREEZE.json').write_text(json.dumps(hashes,indent=2))
auditors={n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in ['audit_cache_stream.py','snapshot_cpu_stats.py','collect_stream.py','watch_cache_live.py','audit_control.py']};(R/'ADDITIONAL_AUDITOR_FREEZE.json').write_text(json.dumps(auditors,indent=2))
(R/'NATIVE_QUEUE_READY.json').write_text(json.dumps(dict(state='PREPARED_NOT_STARTED_WAIT_V5_PASS',prepared=time.time(),source=str(V5),numeric_changes=False,original_BF16=True,host_GiB=128,HB_GiB=8,full_steps_1_7=False),indent=2));print('NATIVE_LIFETIME_PREPARED_NOT_STARTED')

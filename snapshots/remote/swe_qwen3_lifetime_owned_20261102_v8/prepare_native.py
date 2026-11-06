import json,shutil,hashlib,time
from pathlib import Path
R=Path(__file__).resolve().parent;V=R.parent/'swe_qwen3_continuous_portable_20261101_v7'
assert json.loads((R/'OWNED_CONTROL_AUDIT.json').read_text())['state']=='PASS_LIMITED_CPU_TWO_LAYER_KV_OWNERSHIP'
assert json.loads((R/'ENDPOINT_AUDIT.json').read_text())['state']=='PASS_LIMITED_NATIVE_ENDPOINT_TEARDOWN'
assert not (R/'NATIVE_QUEUE_READY.json').exists()
protected={'host','host.cpp','gateway','gateway.cpp','bridge_full.cpp','libfull.so','cpu_services.h','cpu_probe.cpp','libcpu_probe.so','CPU_BUILD_COMMAND.json','BRIDGE_BUILD_COMMAND.json','CPU_VECTORIZATION.log'}
original=json.loads((V/'FREEZE.json').read_text())
for name in original:
 if name in protected or name=='WORKER_FREEZE.json':continue
 src=V/name;dst=R/name
 if str(name).startswith('data/') and (R/'data').is_symlink():
  (R/'data').unlink();shutil.copytree(V/'data',R/'data',symlinks=True)
 dst.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(src,dst)
if (R/'data').is_symlink():
 (R/'data').unlink();shutil.copytree(V/'data',R/'data',symlinks=True)
for name in ['supervise.py','snapshot_cpu_stats.py','watch_cache_live.py','collect_stream.py','audit_raw_when_ready.py','audit_cache_stream.py','audit_full.py','audit_clock.py','validate_lowering.py','check_case.py','phase2_gate.py','peer.py','worker.py','EXTERNAL_DEPENDENCIES.json']:
 if name not in protected:shutil.copy2(V/name,R/name)
p=R/'worker.py';s=p.read_text();assert 'from integrated_adapter import FullAdapter,UnifiedKV' in s
s=s.replace('from integrated_adapter import FullAdapter,UnifiedKV','from owned_adapter import FullAdapter,UnifiedKV').replace('   sy=layers[i]','   a.layer_barrier(phase,i)\n   sy=layers[i]')
p.write_text(s)
p=R/'check_case.py';s=p.read_text();needle="  if i:assert nodes[i-1]['offset']+nodes[i-1]['bytes']<=n['offset']";assert needle in s
p.write_text(s.replace(needle,"  assert n['retired_at']>=n['last_consumer_barrier_start']>=max([n['ready']]+[v['done'] for v in n['readers']])"))
(R/'unified_full.yml').write_text((V/'unified_full.yml').read_text().replace(str(V),str(R)))
p=R/'collect_stream.py';s=p.read_text();needle=' rounds=[validate(R,i) for i in [1,2]]';assert needle in s
s=s.replace(needle,needle+"\n for i in [1,2]:\n  with (R/('native_owned_round%d.log'%i)).open('w') as f:c=subprocess.run(['python3',str(R/'audit_owned.py'),'case%d'%i],stdout=f,stderr=subprocess.STDOUT,timeout=600)\n  assert c.returncode==0,('native ownership audit',i)\n")
p.write_text(s.replace('dynamic_reclamation=False','dynamic_reclamation=True'))
# Freeze the reused independent allocation audit locally; runtime must not depend on mutable v6 sources.
s=(R.parent/'swe_qwen3_lifetime_20261101_v6/audit_control.py').read_text();(R/'allocation_audit_source.py').write_text(s)
p=R/'audit_owned.py';s=p.read_text().replace("(V/'audit_control.py').read_text()","(R/'allocation_audit_source.py').read_text()");p.write_text(s)
names=set(original)-{'WORKER_FREEZE.json'}
names.update(['owned_adapter.py','lifetime_adapter.py','lifetime_allocator.h','LIFETIME_PLAN.json','LIFETIME_FREEZE.json','audit_owned.py','allocation_audit_source.py','OWNED_CONTROL_AUDIT.json','ENDPOINT_AUDIT.json','OWNER_CONTROLS.log','supervise.py','collect_stream.py','snapshot_cpu_stats.py','watch_cache_live.py','audit_raw_when_ready.py','audit_cache_stream.py'])
hashes={n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in sorted(names)}
(R/'WORKER_FREEZE.json').write_text(json.dumps(hashes,indent=2));hashes['WORKER_FREEZE.json']=hashlib.sha256((R/'WORKER_FREEZE.json').read_bytes()).hexdigest();(R/'FREEZE.json').write_text(json.dumps(hashes,indent=2))
(R/'ADDITIONAL_AUDITOR_FREEZE.json').write_text(json.dumps({n:hashes[n] for n in ['audit_cache_stream.py','snapshot_cpu_stats.py','watch_cache_live.py','collect_stream.py','audit_owned.py','allocation_audit_source.py']},indent=2))
(R/'NATIVE_QUEUE_READY.json').write_text(json.dumps(dict(state='PREPARED_NOT_STARTED_WAIT_V7_PASS',prepared=time.time(),baseline=str(V),original_BF16=True,host_GiB=128,HB_GiB=8,full_steps_1_7=False),indent=2))
print('PREPARED_NOT_STARTED_WAIT_V7_PASS')

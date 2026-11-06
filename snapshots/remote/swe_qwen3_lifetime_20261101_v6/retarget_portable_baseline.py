import json,hashlib,shutil
from pathlib import Path
R=Path(__file__).resolve().parent;V7=R.parent/'swe_qwen3_continuous_portable_20261101_v7';assert not (R/'RUN_PID.json').exists()
H=R/'auditor_history';H.mkdir(exist_ok=True)
for name in ['FREEZE.json','WORKER_FREEZE.json','ADDITIONAL_AUDITOR_FREEZE.json','unified_full.yml','collect_stream.py','queue_after_v5.py','EXTERNAL_DEPENDENCIES.json']:
 shutil.copy2(R/name,H/('before_portable_'+name))
cfg=json.loads((R/'unified_full.yml').read_text());new=json.loads((V7/'unified_full.yml').read_text());cfg['phase1'][0]=json.loads(json.dumps(new['phase1'][0]).replace(str(V7),str(R)));(R/'unified_full.yml').write_text(json.dumps(cfg,indent=2))
for name in ['supervise.py','snapshot_cpu_stats.py','watch_cache_live.py','collect_stream.py','audit_raw_when_ready.py','audit_cache_stream.py','audit_full.py','ISA_OBSERVER_BINDING.json','CPU_ADDRESS_IDENTITY_PREFLIGHT.json','EAGER_BINDING_AUDIT_guard.json','ISA_OBSERVER_TRACE.cc']:shutil.copy2(V7/name,R/name)
p=R/'collect_stream.py';s=p.read_text();needle=' rounds=[validate(R,i) for i in [1,2]]';assert needle in s
s=s.replace(needle,needle+"\n for i in [1,2]:\n  with (R/('native_lifetime_round%d.log'%i)).open('w') as f:c=subprocess.run(['python3',str(R/'audit_control.py'),'case%d'%i],stdout=f,stderr=subprocess.STDOUT,timeout=600)\n  assert c.returncode==0,('native lifetime audit',i)\n")
s=s.replace('dynamic_reclamation=False','dynamic_reclamation=True');p.write_text(s)
(R/'EXTERNAL_DEPENDENCIES.json').write_bytes((V7/'EXTERNAL_DEPENDENCIES.json').read_bytes())
p=R/'queue_after_v5.py';s=p.read_text().replace("V5=R.parent/'swe_qwen3_continuous_cache_20261101_v5'","V5=R.parent/'swe_qwen3_continuous_portable_20261101_v7'").replace('91500','136000');s=s.replace(" assert json.loads((R/'NATIVE_QUEUE_READY.json')", " assert all(v['ISA_nehalem_rejected']==0 and v['ISA_supported_decoded_occurrences']>0 for v in json.loads((V5/'CACHE_CHAIN_AUDIT.json').read_text())['rounds'])\n assert json.loads((R/'NATIVE_QUEUE_READY.json')");p.write_text(s)
(R/'PORTABLE_QUEUE_AMENDMENT.json').write_text(json.dumps(dict(state='QUEUED_NOT_NATIVE_PASS',baseline=str(V7),source_precision='original BF16',host_GiB=128,HB_GiB=8,ISA='all ROI instructions checked against XED NEHALEM, unsupported aborts; pre-ROI setup excluded',ASLR='disabled for CPU experiment process only; two-round address equality required',native_bound_seconds=129600,contract='same known finite reader DAG; source routing freely computed and signature checked; no unseen-routing claim',full_steps_1_7=False),indent=2))
f=json.loads((R/'FREEZE.json').read_text());f.pop('WORKER_FREEZE.json',None)
for name in ['audit_cache_stream.py','snapshot_cpu_stats.py','watch_cache_live.py','collect_stream.py','ISA_OBSERVER_BINDING.json','CPU_ADDRESS_IDENTITY_PREFLIGHT.json','EAGER_BINDING_AUDIT_guard.json','ISA_OBSERVER_TRACE.cc','queue_after_v5.py','PORTABLE_QUEUE_AMENDMENT.json']:f[name]=''
for n in f:f[n]=hashlib.sha256((R/n).read_bytes()).hexdigest()
(R/'WORKER_FREEZE.json').write_text(json.dumps(f,indent=2));f['WORKER_FREEZE.json']=hashlib.sha256((R/'WORKER_FREEZE.json').read_bytes()).hexdigest();(R/'FREEZE.json').write_text(json.dumps(f,indent=2))
(R/'ADDITIONAL_AUDITOR_FREEZE.json').write_text(json.dumps({n:f[n] for n in ['audit_cache_stream.py','snapshot_cpu_stats.py','watch_cache_live.py','collect_stream.py','audit_control.py']},indent=2));print('PORTABLE_LIFETIME_QUEUE_PREPARED_NOT_STARTED')

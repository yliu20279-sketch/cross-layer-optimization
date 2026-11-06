import json,hashlib,subprocess,shutil,os
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent;V5=B/'swe_qwen3_continuous_cache_20261101_v5';V6=B/'swe_qwen3_lifetime_20261101_v6';S=V6/'sniper_isa_candidate'
assert not (R/'FREEZE.json').exists()
admission=json.loads((V6/'EAGER_BINDING_AUDIT_guard.json').read_text());assert admission['state']=='PASS_LIMITED_PORTABLE_ROI_ISA_AND_AVX_REJECTION'
frozen=json.loads((V5/'FREEZE.json').read_text())
for n,h in frozen.items():
 p=V5/n;assert hashlib.sha256(p.read_bytes()).hexdigest()==h,n
 q=R/n;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
for n in ['audit_cache_stream.py','snapshot_cpu_stats.py','collect_stream.py','watch_cache_live.py','poll_delivery.py','preflight.py','cpu_negative_controls.py']:shutil.copy2(V5/n,R/n)
for n in ['EXP16_ALL_FP32.bin','SILU_ALL_BF16.bin','oracle_cpu']:os.symlink(str(V5/n),str(R/n))
for n in ['ISA_OBSERVER_TRACE.cc','EAGER_BINDING_AUDIT_guard.json','ISA_OBSERVER_METHOD.json','ISA_GUARD_BUILD_EXIT.json']:shutil.copy2(V6/n,R/n)
cfg=json.loads((R/'unified_full.yml').read_text().replace(str(V5),str(R)));args=cfg['phase1'][0]['args'];args[0]='GLIBC_TUNABLES='+admission['GLIBC_TUNABLES'];args[1]=str(S/'run-sniper');args.insert(1,'LD_BIND_NOW=1');(R/'unified_full.yml').write_text(json.dumps(cfg,indent=2))
cmd=[x.replace(str(V5),str(R)) for x in json.loads((R/'CPU_BUILD_COMMAND.json').read_text())];(R/'CPU_BUILD_COMMAND.json').write_text(json.dumps(cmd,indent=2));subprocess.run(cmd,check=True)
py=B/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
for name in ['preflight.py','cpu_negative_controls.py']:
 with (R/(name+'.log')).open('w') as out:subprocess.run([str(py),str(R/name)],stdout=out,stderr=subprocess.STDOUT,timeout=600,check=True)
binding=dict(state='REPRESENTATIVE_ROI_PASS_FULL_ROI_REQUIRED',GLIBC_TUNABLES=admission['GLIBC_TUNABLES'],LD_BIND_NOW='1',observer=str(S/'lib/sniper'),observer_sha256=hashlib.sha256((S/'lib/sniper').read_bytes()).hexdigest(),scope='all actual SIFT-decoded ROI instructions must be supported by bundled XED NEHALEM; dynamic binding and mmap setup excluded from ROI; no startup latency/ISA claim',negative_AVX_detected=True)
(R/'ISA_OBSERVER_BINDING.json').write_text(json.dumps(binding,indent=2))
ext=json.loads((R/'EXTERNAL_DEPENDENCIES.json').read_text())
for p in [S/'lib/sniper',S/'common/trace_frontend/trace_thread.cc']:ext[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
(R/'EXTERNAL_DEPENDENCIES.json').write_text(json.dumps(ext,indent=2))
p=R/'watch_cache_live.py';s=p.read_text();s=s.replace("assert '*ERROR*' not in line and 'Assertion' not in line","assert 'ISA_NEHALEM_REJECTED' not in line and '*ERROR*' not in line and 'Assertion' not in line");p.write_text(s)
p=R/'audit_cache_stream.py';s=p.read_text();needle="final_cpu_fs=values[0][0];db.close()";assert needle in s
s=s.replace(needle,"final_cpu_fs=values[0][0]\n isa_rows=db.execute(\"select n.objectname,n.metricname,v.value from [values] v join names n using(nameid) join prefixes p using(prefixid) where p.prefixname='roi-end' and v.core=0 and n.objectname in ('decoded_isa_nehalem_ok','decoded_isa_nehalem_rejected')\").fetchall();db.close()\n assert isa_rows and not any(v for o,n,v in isa_rows if o=='decoded_isa_nehalem_rejected')\n isa_supported=sum(v for o,n,v in isa_rows if o=='decoded_isa_nehalem_ok');assert isa_supported>0")
s=s.replace('CPU_cache_gates=drain_count,','CPU_cache_gates=drain_count,ISA_nehalem_rejected=0,ISA_supported_decoded_occurrences=isa_supported,');p.write_text(s)
# Exclude only the tooling source tree if a later lifetime run uses this collector.
p=R/'collect_stream.py';s=p.read_text().replace("if p.is_file() and '__pycache__' not in p.parts", "if p.is_file() and '__pycache__' not in p.parts and 'sniper_isa_candidate' not in p.parts");p.write_text(s)
(R/'PORTABILITY_AMENDMENT.json').write_text(json.dumps(dict(state='PREREGISTERED_NOT_RUN',replaces=str(V5),stopped_baseline=json.loads((V5/'STOP_AMENDMENT.json').read_text()),numeric_changes=False,original_BF16=True,host_GiB=128,HB_GiB=8,changes=['use actual glibc2.31 usable-feature dispatch selectors','bind dynamic libraries during pre-ROI setup','observe every actual decoded ROI instruction with XED NEHALEM','stop on first unsupported ISA event; final SQLite independently checked'],GPU_differences='retained',no_tolerance_change=True,full_steps_1_7=False),indent=2))
names=[n for n in frozen if n!='WORKER_FREEZE.json']+['audit_cache_stream.py','snapshot_cpu_stats.py','collect_stream.py','watch_cache_live.py','ISA_OBSERVER_BINDING.json','PORTABILITY_AMENDMENT.json','ISA_OBSERVER_TRACE.cc','EAGER_BINDING_AUDIT_guard.json']
hashes={n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in names};(R/'WORKER_FREEZE.json').write_text(json.dumps(hashes,indent=2));hashes['WORKER_FREEZE.json']=hashlib.sha256((R/'WORKER_FREEZE.json').read_bytes()).hexdigest();(R/'FREEZE.json').write_text(json.dumps(hashes,indent=2))
(R/'ADDITIONAL_AUDITOR_FREEZE.json').write_text(json.dumps({n:hashes[n] for n in ['audit_cache_stream.py','snapshot_cpu_stats.py','collect_stream.py','watch_cache_live.py']},indent=2))
(R/'CANDIDATE_READY.json').write_text(json.dumps(dict(state='PORTABLE_CPU_BUILD_PREFLIGHT_ONLY',native_full_layers=0,full_steps_1_7=False),indent=2));print('PORTABLE_BASELINE_PREPARED_NOT_RUN')

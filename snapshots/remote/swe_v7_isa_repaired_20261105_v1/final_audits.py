import json,subprocess,time,sqlite3,shutil,hashlib,traceback
from pathlib import Path
R=Path(__file__).resolve().parent;deadline=time.monotonic()+7200
try:
 assert json.loads((R/'RUN_EXIT.json').read_text())['returncode']==0
 for iteration in [1,2]:
  proc=R/'run1'/f'proc_r{iteration}_p1_t0';d=R/f'case{iteration}'
  a=sqlite3.connect(str(proc/'sniper_stats/sim.stats.sqlite3'));b=sqlite3.connect(str(d/'CPU_FINAL_STATS.sqlite3'));a.backup(b);b.close();a.close()
  shutil.copy2(proc/'sniper_stats/sim.cfg',d/'CPU_FINAL_CONFIG.cfg')
 for name in ['audit_raw_when_ready.py','audit_clock.py','audit_cache_stream.py']:
  with (R/(name+'.final.log')).open('w') as log:
   p=subprocess.run(['python3',str(R/name)],cwd=R,stdout=log,stderr=subprocess.STDOUT,timeout=max(1,deadline-time.monotonic()))
   if p.returncode:raise RuntimeError((name,p.returncode))
 for path,digest in json.loads((R/'NEW_RUNTIME_BINDING.json').read_text()).items():
  assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
 for name in ['RAW_ORACLE_AUDIT.json','CLOCK_AUDIT.json','CACHE_CHAIN_AUDIT.json','BASE_INDEPENDENT_AUDIT.json','LIVE_CACHE_DONE.json']:assert (R/name).exists()
 (R/'FINAL_DELIVERY.json').write_text(json.dumps(dict(state='PASS_LIMITED_CONTINUOUS_TWO_LAYER_ISA_CACHE_CLOCK',full_system_cost=False,formal_matrix_runs=0),indent=2))
except Exception:
 (R/'FINAL_AUDIT_FAILURE.txt').write_text(traceback.format_exc())
 (R/'FINAL_DELIVERY.json').write_text(json.dumps(dict(state='FAIL_FINAL_AUDIT',full_model_pass=False)))
 raise

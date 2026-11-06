import time,json,hashlib,subprocess,traceback,os
from pathlib import Path
R=Path(__file__).resolve().parent;V5=R.parent/'swe_qwen3_continuous_cache_20261101_v5';deadline=time.monotonic()+91500
def write(v):(R/'QUEUE_STATUS.json').write_text(json.dumps(v,indent=2))
write(dict(state='WAITING_V5_STRICT_FINAL_PASS',target_native_runs=0,full_steps_1_7=False))
try:
 while not (V5/'SAFE_DELIVERY_STATUS.json').exists():
  for n in ['RAW_ORACLE_FAILURE.txt','LIVE_CACHE_FAILURE.txt','STREAM_COLLECTOR_FAILURE.txt','CPU_STATS_SNAPSHOT_FAILURE.txt']:
   if (V5/n).exists():raise RuntimeError('baseline failed: '+n+'; queued experiment not started')
  if (V5/'RUN_EXIT.json').exists():
   v=json.loads((V5/'RUN_EXIT.json').read_text());assert v['returncode']==0 and v['reason'] is None,v
  if time.monotonic()>deadline:raise TimeoutError('baseline final PASS wait expired; no second run started')
  time.sleep(15)
 assert json.loads((V5/'SAFE_DELIVERY_STATUS.json').read_text())['state']=='PASS_LIMITED_FULL_FUNCTIONAL_CPU_FP32_SRAM_SAFE_REVIEW'
 assert json.loads((V5/'CACHE_CHAIN_AUDIT.json').read_text())['state']=='PASS_LIMITED_FULL_TWO_LAYER_CACHE_AND_ALIAS_CHAIN'
 assert json.loads((V5/'RAW_ORACLE_AUDIT.json').read_text())['state']=='PASS_LIMITED_759_FP32_MATRICES_AND_56_STAGES_TWO_ROUND'
 assert json.loads((R/'NATIVE_QUEUE_READY.json').read_text())['state']=='PREPARED_NOT_STARTED_WAIT_V5_PASS'
 for n,h in json.loads((R/'FREEZE.json').read_text()).items():assert hashlib.sha256((R/n).read_bytes()).hexdigest()==h,n
 assert not (R/'RUN_PID.json').exists()
 jobs={}
 for name in ['supervise.py','audit_raw_when_ready.py','snapshot_cpu_stats.py','watch_cache_live.py','collect_stream.py']:
  with (R/(name+'.log')).open('w') as f:p=subprocess.Popen(['python3',str(R/name)],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  jobs[name]=p.pid
 (R/'BACKGROUND_JOBS.json').write_text(json.dumps(jobs,indent=2));write(dict(state='NATIVE_LIFETIME_LAUNCHED_NOT_PASS',jobs=jobs,full_steps_1_7=False,scope='sequential second experiment,24h bound, after strict baseline completion'));print(json.dumps(jobs),flush=True)
except Exception:write(dict(state='NOT_STARTED_BASELINE_OR_QUEUE_GATE_FAILED',reason=traceback.format_exc(),full_steps_1_7=False));raise

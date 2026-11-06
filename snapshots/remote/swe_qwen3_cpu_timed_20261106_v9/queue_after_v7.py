import time,json,hashlib,subprocess,traceback
from pathlib import Path
R=Path(__file__).resolve().parent;V=R.parent/'swe_qwen3_continuous_portable_20261103_v7_ackfix';deadline=time.monotonic()+136000
def j(p):return json.loads(p.read_text())
def write(v):(R/'QUEUE_STATUS.json').write_text(json.dumps(v,indent=2))
write(dict(state='WAITING_V7_STRICT_FINAL_PASS',target_native_runs=0,full_steps_1_7=False))
try:
 while not (V/'SAFE_DELIVERY_STATUS.json').exists():
  for name in ['RAW_ORACLE_FAILURE.txt','LIVE_CACHE_FAILURE.txt','STREAM_COLLECTOR_FAILURE.txt','CPU_STATS_SNAPSHOT_FAILURE.txt']:
   if (V/name).exists():raise RuntimeError('baseline failed: '+name)
  if (V/'RUN_EXIT.json').exists():assert j(V/'RUN_EXIT.json')['returncode']==0 and j(V/'RUN_EXIT.json')['reason'] is None
  if time.monotonic()>deadline:raise TimeoutError('baseline strict final PASS wait expired; candidate not started')
  time.sleep(15)
 assert j(V/'SAFE_DELIVERY_STATUS.json')['state']=='PASS_LIMITED_FULL_FUNCTIONAL_CPU_FP32_SRAM_SAFE_REVIEW'
 cache=j(V/'CACHE_CHAIN_AUDIT.json');assert cache['state']=='PASS_LIMITED_FULL_TWO_LAYER_CACHE_AND_ALIAS_CHAIN'
 assert len(cache['rounds'])==2 and all(v['ISA_nehalem_rejected']==0 and v['ISA_supported_decoded_occurrences']>0 for v in cache['rounds'])
 assert j(V/'RAW_ORACLE_AUDIT.json')['state']=='PASS_LIMITED_759_FP32_MATRICES_AND_56_STAGES_TWO_ROUND'
 assert j(R/'NATIVE_QUEUE_READY.json')['state']=='PREPARED_NOT_STARTED_WAIT_V7_PASS'
 for n,h in j(R/'FREEZE.json').items():assert hashlib.sha256((R/n).read_bytes()).hexdigest()==h,n
 assert not (R/'RUN_PID.json').exists()
 jobs={}
 for name in ['supervise.py','audit_raw_when_ready.py','snapshot_cpu_stats.py','watch_cache_live.py','collect_stream.py']:
  with (R/(name+'.log')).open('w') as f:p=subprocess.Popen(['python3',str(R/name)],cwd=R,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  jobs[name]=p.pid
 (R/'BACKGROUND_JOBS.json').write_text(json.dumps(jobs,indent=2));write(dict(state='NATIVE_OWNED_LIFETIME_LAUNCHED_NOT_PASS',jobs=jobs,full_steps_1_7=False,bound_seconds=129600))
except Exception:
 write(dict(state='NOT_STARTED_BASELINE_OR_QUEUE_GATE_FAILED',reason=traceback.format_exc(),full_steps_1_7=False));raise

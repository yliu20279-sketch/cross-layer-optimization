from pathlib import Path
import os,json,time,signal,subprocess,traceback,re
R=Path(__file__).resolve().parent;B=R.parent
def stop(p):
 try:
  if p.poll() is None:os.killpg(p.pid,signal.SIGTERM)
 except ProcessLookupError:pass
try:
 W=R/'run1';W.mkdir()
 env=dict(os.environ,SIMULATOR_ROOT='/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO',SWE_REQUIRE_NONEMPTY_DELAY='1',SWE_DOMAIN_SERVICES='1',SWE_CANONICAL_XY='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
 start=time.monotonic();reason=None
 with (R/'RUN.log').open('w') as log:
  p=subprocess.Popen([str(B/'swe_qwen3_legosim_clock_fix_20261030_v1/build/interchiplet'),str(R/'unified_full.yml'),'-t','2','-e','0','-w','4','-H','13','-f','4'],cwd=W,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  (R/'RUN_PID.json').write_text(json.dumps(dict(pid=p.pid,bound_seconds=129600)))
  watchlog=(R/'watch_cache_live.log').open('w')
  watcher=subprocess.Popen(['python3',str(R/'watch_cache_live.py')],cwd=R,stdout=watchlog,stderr=subprocess.STDOUT,start_new_session=True)
  while p.poll() is None:
   bad=[int(v) for v in re.findall(r'terminate with status = (\d+)',(R/'RUN.log').read_text()) if int(v)]
   if bad or watcher.poll() not in (None,0) or time.monotonic()-start>129600:
    reason='child_failure_'+str(bad[0]) if bad else 'cache_or_ISA_audit_failure' if watcher.poll() not in (None,0) else 'bounded_36h_timeout'
    stop(p);break
   time.sleep(5)
  rc=p.wait(timeout=60)
 (R/'RUN_EXIT.json').write_text(json.dumps(dict(returncode=rc,reason=reason,elapsed_seconds=time.monotonic()-start),indent=2))
 if rc!=0:
  stop(watcher)
  (R/'FINAL_DELIVERY.json').write_text(json.dumps(dict(state='FAIL_OR_BOUND_REACHED',reason=reason,full_model_pass=False)))
 else:
  watcher.wait(timeout=120)
  if watcher.returncode:raise RuntimeError('watcher final failed')
  with (R/'FINAL_AUDIT_CONTROLLER.log').open('w') as log:
   result=subprocess.run(['python3',str(R/'final_audits.py')],cwd=R,stdout=log,stderr=subprocess.STDOUT,timeout=7300)
  if result.returncode:raise RuntimeError('final audit failed')
except Exception:
 (R/'CONTROLLER_FAILURE.txt').write_text(traceback.format_exc())
 raise

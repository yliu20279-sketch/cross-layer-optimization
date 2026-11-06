import os,time,json,subprocess,signal,re,sys
from pathlib import Path
R=Path('/mnt/sda1/h3240101068/swe_v7_log_repair_20261105_v1');negative=len(sys.argv)>1 and sys.argv[1]=='negative';P=R/('endpoint_negative' if negative else 'endpoint_positive_v2');W=P/'run1';W.mkdir(exist_ok=False)
env=dict(os.environ,SIMULATOR_ROOT='/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO',SWE_REQUIRE_NONEMPTY_DELAY='1',SWE_DOMAIN_SERVICES='1',SWE_CANONICAL_XY='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
start=time.time();reason=None
if negative:env['SWE_LEAK_OWNER']='1'
with (P/'RUN.log').open('w') as f:
 p=subprocess.Popen(['/mnt/sda1/h3240101068/swe_qwen3_legosim_clock_fix_20261030_v1/build/interchiplet',str(P/'probe.yml'),'-t','2','-e','0','-w','4','-H','13','-f','4'],cwd=W,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 (P/'RUN_PID.json').write_text(json.dumps(dict(pid=p.pid,bound_seconds=1200)))
 while p.poll() is None:
  bad=next((int(v) for v in re.findall(r'terminate with status = (\d+)',(P/'RUN.log').read_text()) if int(v)),None)
  if bad is not None or time.time()-start>1200:
   reason='child_failure_'+str(bad) if bad is not None else 'bounded_1200s_timeout';os.killpg(p.pid,signal.SIGTERM);break
  time.sleep(3)
 rc=p.wait(timeout=30)
(P/'RUN_EXIT.json').write_text(json.dumps(dict(returncode=rc,reason=reason,elapsed_seconds=time.time()-start,scope='endpoint smoke only; not model validation'),indent=2))

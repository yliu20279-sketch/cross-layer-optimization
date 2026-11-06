from pathlib import Path
import os,json,time,signal,subprocess
p=Path(__file__).resolve().parent
w=p/'bounded_run';w.mkdir()
env=dict(os.environ,SIMULATOR_ROOT='/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO',SWE_REQUIRE_NONEMPTY_DELAY='1',SWE_DOMAIN_SERVICES='1',SWE_CANONICAL_XY='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
with (p/'BOUNDED_RUN.log').open('w') as log:
 q=subprocess.Popen(['/mnt/sda1/h3240101068/swe_qwen3_legosim_clock_fix_20261030_v1/build/interchiplet',str(p/'unified_full.yml'),'-t','2','-e','0','-w','4','-H','13','-f','4'],cwd=w,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 (p/'PREFIX_PID.json').write_text(json.dumps(dict(pid=q.pid,bound_seconds=180)))
 start=time.monotonic();reason=None
 while q.poll() is None:
  if 'terminate with status = 256' in (p/'BOUNDED_RUN.log').read_text():reason='child_failure';os.killpg(q.pid,signal.SIGTERM);break
  if time.monotonic()-start>180:reason='planned_180s_prefix_limit';os.killpg(q.pid,signal.SIGTERM);break
  time.sleep(2)
 rc=q.wait(timeout=30)
 (p/'PREFIX_EXIT.json').write_text(json.dumps(dict(returncode=rc,reason=reason,elapsed=time.monotonic()-start,full_model_pass=False),indent=2))

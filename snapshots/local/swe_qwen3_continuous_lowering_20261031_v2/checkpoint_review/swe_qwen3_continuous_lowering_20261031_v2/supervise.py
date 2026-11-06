import os,time,json,subprocess,signal,hashlib,re
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent
for n,h in json.loads((R/'FREEZE.json').read_text()).items():assert hashlib.sha256((R/n).read_bytes()).hexdigest()==h
W=R/'run1';W.mkdir(exist_ok=False);env=dict(os.environ,SIMULATOR_ROOT='/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO',SWE_REQUIRE_NONEMPTY_DELAY='1',SWE_DOMAIN_SERVICES='1',SWE_CANONICAL_XY='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
start=time.time();reason=None
with (R/'RUN.log').open('w') as f:
 p=subprocess.Popen([str(B/'swe_qwen3_legosim_clock_fix_20261030_v1/build/interchiplet'),str(R/'unified_full.yml'),'-t','2','-e','0','-w','4','-H','13','-f','4'],cwd=W,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 (R/'RUN_PID.json').write_text(json.dumps(dict(pid=p.pid,bound_seconds=43200)))
 while p.poll() is None:
  bad=next((int(v) for v in re.findall(r'terminate with status = (\d+)',(R/'RUN.log').read_text()) if int(v)),None)
  if bad is not None or time.time()-start>43200:
   reason=('child_failure_'+str(bad)) if bad is not None else 'bounded_43200s_timeout';os.killpg(p.pid,signal.SIGTERM);break
  time.sleep(5)
 rc=p.wait(timeout=30)
(R/'RUN_EXIT.json').write_text(json.dumps(dict(returncode=rc,reason=reason,elapsed_seconds=time.time()-start),indent=2));print('FULL_EXIT',rc,reason,flush=True)

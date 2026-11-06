import os,subprocess,json,time,signal,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent
assert all(hashlib.sha256((R/n).read_bytes()).hexdigest()==h for n,h in json.loads((R/'FREEZE.json').read_text()).items())
W=R/'run1';W.mkdir(exist_ok=False)
env=dict(os.environ,SIMULATOR_ROOT='/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO',SWE_REQUIRE_NONEMPTY_DELAY='1',SWE_DOMAIN_SERVICES='1',SWE_CANONICAL_XY='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
start=time.time()
with (R/'RUN.log').open('w') as f:
 p=subprocess.Popen([str(R.parent/'swe_qwen3_legosim_clock_fix_20261030_v1/build/interchiplet'),str(R/'unified.yml'),'-t','2','-e','0','-w','4','-H','13','-f','4'],cwd=W,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 (R/'RUN_PID.json').write_text(json.dumps(dict(pid=p.pid,scope=str(R))))
 try:rc=p.wait(timeout=1200)
 except subprocess.TimeoutExpired:
  os.killpg(p.pid,signal.SIGTERM);rc=p.wait(timeout=30)
(R/'RUN_EXIT.json').write_text(json.dumps(dict(returncode=rc,elapsed_seconds=time.time()-start)))
print('UNIFIED_EXIT',rc,flush=True)
raise SystemExit(rc)

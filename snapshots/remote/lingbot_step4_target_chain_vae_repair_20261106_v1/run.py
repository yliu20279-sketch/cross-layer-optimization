
import os,json,time,subprocess,signal,traceback
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent;W=R/'run';W.mkdir()
env=dict(os.environ,SIMULATOR_ROOT='/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO',SWE_DOMAIN_SERVICES='1',SWE_CANONICAL_XY='1',SWE_REQUIRE_NONEMPTY_DELAY='1',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',CUDA_VISIBLE_DEVICES='')
started=time.time()
try:
 with (R/'RUN.log').open('w') as f:
  p=subprocess.Popen([str(B/'swe_qwen3_legosim_clock_fix_20261030_v1/build/interchiplet'),str(R/'config.yml'),'-t','2','-e','0','-w','4','-H','13','-f','4'],cwd=W,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  try:rc=p.wait(timeout=3600)
  except subprocess.TimeoutExpired:
   os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=20);raise
 (R/'RUN_EXIT.json').write_text(json.dumps(dict(returncode=rc,wall_seconds=time.time()-started),indent=2))
 assert rc==0
 for k in (1,2):assert (R/f'case{k}/N00/PASS.json').exists()
 (R/'STATUS.json').write_text(json.dumps(dict(state='EXECUTED_PENDING_INDEPENDENT_NUMERICAL_AUDIT')))
except BaseException:
 (R/'FAILURE.json').write_text(json.dumps(dict(error=traceback.format_exc()),indent=2))
 raise

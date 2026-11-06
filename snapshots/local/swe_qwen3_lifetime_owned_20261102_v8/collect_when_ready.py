"""Bounded local downloader/verifier for the two explicitly authorized experiments."""
import subprocess,json,time,sys,os,traceback
from pathlib import Path
R=Path(__file__).resolve().parent;deadline=time.monotonic()+78*3600
(R/'AUTO_COLLECTION_NATIVE_SESSION.json').write_text(json.dumps(dict(pid=os.getpid(),started=time.time(),bound_hours=78,mode='hidden local collector; liveness checked in same elevated process domain'),indent=2))
def status(value):(R/'AUTO_COLLECTION_STATUS.json').write_text(json.dumps(value,indent=2))
try:
 for name in ['swe_qwen3_continuous_portable_20261101_v7','swe_qwen3_lifetime_owned_20261102_v8']:
  H=R.parent/name;remote='/mnt/sda1/h3240101068/'+name
  while True:
   if time.monotonic()>deadline:raise TimeoutError('78h local collection bound')
   try:
    c=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','myserver-113','python3 '+remote+'/poll_delivery.py'],capture_output=True,text=True,timeout=60)
    assert c.returncode==0,c.stderr[-1000:];value=json.loads(c.stdout)
    if value['state']=='FAILED':raise RuntimeError(json.dumps(value))
    if value['state']=='PASS_LIMITED_FULL_FUNCTIONAL_CPU_FP32_SRAM_SAFE_REVIEW':break
    status(dict(state='WAITING_REMOTE_STRICT_AUDITS',experiment=name,remote=value))
   except (subprocess.TimeoutExpired,AssertionError,json.JSONDecodeError) as e:status(dict(state='RETRYING_READ_ONLY_REMOTE_STATUS',experiment=name,reason=str(e)))
   time.sleep(60)
  assert value['archive']==remote+'_SAFE_REVIEW.tar.gz'
  (H/'REMOTE_DELIVERY_STATUS.json').write_text(json.dumps(value,indent=2))
  target=H/(name+'_SAFE_REVIEW.tar.gz');partial=Path(str(target)+'.partial')
  if not target.exists():
   subprocess.run(['scp','-o','BatchMode=yes','-o','ConnectTimeout=15','myserver-113:'+value['archive'],str(partial)],check=True,timeout=3600);os.replace(partial,target)
  status(dict(state='VERIFYING_LOCAL_REVIEW',experiment=name))
  with (H/'LOCAL_VERIFY.log').open('w') as f:subprocess.run([sys.executable,str(R/'verify_delivery_local.py'),str(H)],stdout=f,stderr=subprocess.STDOUT,check=True,timeout=7200)
 status(dict(state='BOTH_LOCAL_REVIEWS_COMPLETE_LIMITED',experiments=2,full_steps_1_7=False))
except Exception:
 status(dict(state='COLLECTION_OR_VERIFICATION_FAILED_NO_PROMOTION',reason=traceback.format_exc(),full_steps_1_7=False));raise

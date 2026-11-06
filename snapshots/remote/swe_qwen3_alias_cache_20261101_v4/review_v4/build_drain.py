import subprocess,json,hashlib,time,sys
from pathlib import Path
R=Path(__file__).resolve().parent;S=R/'sniper_drain_candidate'
out=[]
with (R/'DRAIN_BUILD_V2.log').open('w') as f:
 for part in ['common','standalone']:
  cmd=['make','-j4','-C',str(S/part)]
  if '--force' in sys.argv:cmd.insert(1,'-B')
  try:c=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=1200);rc=c.returncode
  except subprocess.TimeoutExpired:rc=124
  out.append(dict(command=cmd,returncode=rc))
  if rc:break
passed=len(out)==2 and all(x['returncode']==0 for x in out)
result=dict(state='BUILD_ONLY_NOT_FUNCTIONAL_PASS' if passed else 'BUILD_FAILED',commands=out)
if passed:result['sniper_sha256']=hashlib.sha256((S/'lib/sniper').read_bytes()).hexdigest()
(R/'DRAIN_BUILD_EXIT.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))

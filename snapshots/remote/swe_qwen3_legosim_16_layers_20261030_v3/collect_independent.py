"""Survive client disconnects; audit completed runs without restarting them."""
import time,json,subprocess,hashlib,tarfile,traceback
from pathlib import Path
R=Path(__file__).resolve().parent;deadline=time.monotonic()+14400
while time.monotonic()<deadline and not (R/'RUN_EXIT.json').exists():time.sleep(10)
try:
 status=json.loads((R/'RUN_EXIT.json').read_text());assert status['returncode']==0 and status['reason'] is None,status
 # Allow the normal supervisor to publish its result first.
 for _ in range(6):
  if (R/'DELIVERY_STATUS.json').exists():break
  time.sleep(10)
 c=subprocess.run(['python3',str(R/'audit_clock.py')],capture_output=True,text=True)
 (R/'COLLECTOR_AUDIT.json').write_text(json.dumps(dict(returncode=c.returncode,stdout=c.stdout,stderr=c.stderr),indent=2));assert c.returncode==0,c.stderr
 members=[p for p in sorted(R.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name not in ['COLLECTOR.log','COMPLETE_MANIFEST.json','COMPLETE_DELIVERY.json'] and (p.stat().st_size<40*2**20 or p.suffix in ['.csv','.json','.bin'])]
 manifest=[dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in members]
 (R/'COMPLETE_MANIFEST.json').write_text(json.dumps(manifest,indent=2));pack=R.parent/(R.name+'_COMPLETE_REVIEW.tar.gz')
 with tarfile.open(pack,'w:gz') as t:
  for p in members+[R/'COMPLETE_MANIFEST.json']:t.add(p,arcname=R.name+'/'+str(p.relative_to(R)))
 out=dict(state='PASS_LIMITED_INDEPENDENT_FULL_LAYER_REVIEW',archive=str(pack),bytes=pack.stat().st_size,sha256=hashlib.sha256(pack.read_bytes()).hexdigest(),members=len(members),full_steps_1_7=False)
 (R/'COMPLETE_DELIVERY.json').write_text(json.dumps(out,indent=2));print(json.dumps(out),flush=True)
except Exception:
 (R/'COLLECTOR_FAILURE.txt').write_text(traceback.format_exc());raise

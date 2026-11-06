import time,json,hashlib,tarfile,subprocess
from pathlib import Path
P=Path('/mnt/sda1/h3240101068/swe_qwen3_legosim_integration_20261030_v1');R=P/'unified_layers_fifo_v2'
deadline=time.monotonic()+3700;gate_done=False
while time.monotonic()<deadline:
 if not gate_done and (R/'case1/UNIFIED_SUMMARY.json').exists():
  c=subprocess.run(['python3',str(P/'phase2_receipt_gate.py'),str(R)],capture_output=True,text=True)
  (R/'APPLICATION_GATE.json').write_text(json.dumps(dict(returncode=c.returncode,stdout=c.stdout,stderr=c.stderr),indent=2));gate_done=True
 if (R/'RUN3_EXIT.json').exists():
  # Supervisor writes exit status before audit; perform a fresh independent audit.
  c=subprocess.run(['python3',str(R/'audit_full.py')],capture_output=True,text=True)
  (R/'COLLECTOR_AUDIT.json').write_text(json.dumps(dict(returncode=c.returncode,stdout=c.stdout,stderr=c.stderr),indent=2))
  state='PASS_LIMITED_UNIFIED_TWO_LAYER_FUNCTIONAL' if c.returncode==0 else 'FAILED_INDEPENDENT_AUDIT'
  manifest=[];members=[]
  for p in sorted(R.rglob('*')):
   if not p.is_file() or '__pycache__' in p.parts or p.stat().st_size>40*2**20:continue
   members.append(p);manifest.append(dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
  (R/'REVIEW_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
  pack=P/'UNIFIED_LAYERS_FIFO_V2_REVIEW.tar.gz'
  with tarfile.open(pack,'w:gz') as t:
   for p in members+[R/'REVIEW_MANIFEST.json']:t.add(p,arcname='unified_layers_fifo_v2/'+str(p.relative_to(R)))
  out=dict(state=state,archive=str(pack),archive_bytes=pack.stat().st_size,archive_sha256=hashlib.sha256(pack.read_bytes()).hexdigest(),members=len(members),full_steps_1_7=False,scope='one active NPU/HB diagnostic topology; full host and canonical16 target timing pending')
  (R/'DELIVERY_STATUS.json').write_text(json.dumps(out,indent=2));print(json.dumps(out),flush=True);break
 time.sleep(10)
else:
 (R/'COLLECTOR_TIMEOUT.json').write_text(json.dumps(dict(state='BOUNDED_WAIT_EXPIRED_NOT_PASS')))

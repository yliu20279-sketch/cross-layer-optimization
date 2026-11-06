import time,json,subprocess,hashlib,tarfile,traceback,runpy,sys
from pathlib import Path
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R));from validate_lowering import validate
deadline=time.monotonic()+90000
while time.monotonic()<deadline and not (R/'RUN_EXIT.json').exists():time.sleep(10)
try:
 status=json.loads((R/'RUN_EXIT.json').read_text());assert status['returncode']==0 and status['reason'] is None,status
 c=subprocess.run(['/usr/bin/python3',str(R/'audit_clock.py')],capture_output=True,text=True);(R/'COLLECTOR_BASE_AUDIT.json').write_text(json.dumps(dict(returncode=c.returncode,stdout=c.stdout,stderr=c.stderr),indent=2));assert c.returncode==0,c.stderr
 c=subprocess.run(['/usr/bin/python3',str(R/'audit_cache_chain.py')],capture_output=True,text=True);(R/'CACHE_COLLECTOR_RESULT.json').write_text(json.dumps(dict(returncode=c.returncode,stdout=c.stdout,stderr=c.stderr)));assert c.returncode==0,c.stderr
 rows=[validate(R,i) for i in [1,2]];out=dict(state='PASS_LIMITED_FULL_TWO_LAYER_CPU_FP32_SRAM_REVIEW',rounds=rows,original_BF16=True,host_GiB=128,HB_GiB=8,GPU_differences='retained',cache_maintenance_timing_certified=False,full_steps_1_7=False)
 (R/'INDEPENDENT_AUDIT.json').write_text(json.dumps(out,indent=2))
 # Full16GiB math data remains on113 with its complete SHA/provenance; compact review is explicitly a subset.
 members=[p for p in sorted(R.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name not in ['collect.py.log','MANIFEST.json','DELIVERY_STATUS.json'] and p.stat().st_size<40*2**20]
 manifest=[dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in members];(R/'MANIFEST.json').write_text(json.dumps(manifest,indent=2));pack=R.parent/(R.name+'_REVIEW.tar.gz')
 with tarfile.open(pack,'w:gz') as t:
  for p in members+[R/'MANIFEST.json']:t.add(p,arcname=R.name+'/'+str(p.relative_to(R)))
 (R/'DELIVERY_STATUS.json').write_text(json.dumps(dict(state=out['state'],members=len(members),archive=str(pack),bytes=pack.stat().st_size,sha256=hashlib.sha256(pack.read_bytes()).hexdigest(),large_math_data_left_on113=True,full_steps_1_7=False),indent=2));print(json.dumps(out),flush=True)
except Exception:
 (R/'COLLECTOR_FAILURE.txt').write_text(traceback.format_exc());raise

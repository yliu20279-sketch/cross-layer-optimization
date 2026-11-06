import os,time,json,subprocess,signal,hashlib,tarfile
from pathlib import Path
R=Path(__file__).resolve().parent;P=R.parent/'swe_qwen3_legosim_integration_20261030_v1/unified_layers_fifo_v2'
deadline=time.monotonic()+2700
while not (P/'DELIVERY_STATUS.json').exists() and time.monotonic()<deadline:time.sleep(10)
if not (P/'DELIVERY_STATUS.json').exists():raise SystemExit('prerequisite bounded wait expired; target not launched')
pr=json.loads((P/'DELIVERY_STATUS.json').read_text());assert pr['state']=='PASS_LIMITED_UNIFIED_TWO_LAYER_FUNCTIONAL',pr
assert json.loads((P/'COLLECTOR_AUDIT.json').read_text())['returncode']==0
(R/'PREREQUISITE_PASS.json').write_text(json.dumps(pr,indent=2))
assert all(hashlib.sha256((R/n).read_bytes()).hexdigest()==h for n,h in json.loads((R/'FREEZE.json').read_text()).items())
W=R/'run1';W.mkdir(exist_ok=False);env=dict(os.environ,SIMULATOR_ROOT='/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO',SWE_REQUIRE_NONEMPTY_DELAY='1',SWE_DOMAIN_SERVICES='1',SWE_CANONICAL_XY='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
start=time.time();reason=None
with (R/'RUN.log').open('w') as f:
 p=subprocess.Popen([str(R/'build/interchiplet'),str(R/'unified16.yml'),'-t','2','-e','0','-w','4','-H','13','-f','4'],cwd=W,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 try:rc=p.wait(timeout=1200)
 except subprocess.TimeoutExpired:
  reason='bounded_1200s_timeout';os.killpg(p.pid,signal.SIGTERM);rc=p.wait(timeout=30)
(R/'RUN_EXIT.json').write_text(json.dumps(dict(returncode=rc,reason=reason,elapsed_seconds=time.time()-start),indent=2));print('TARGET_EXIT',rc,reason,flush=True)
if rc!=0:raise SystemExit(rc)
c=subprocess.run(['python3',str(R/'audit16_clock.py')],capture_output=True,text=True);(R/'AUDIT.log').write_text(c.stdout+c.stderr);print(c.stdout,c.stderr,flush=True)
if c.returncode:raise SystemExit(c.returncode)
members={p for p in R.rglob('*') if p.is_file() and not any(x in p.parts for x in ['source','build','popnet_xy_source','popnet_xy_build','__pycache__']) and p.stat().st_size<40*2**20}
members.update(R/n for n in json.loads((R/'FREEZE.json').read_text()));members=sorted(members)
manifest=[dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in members]
(R/'MANIFEST.json').write_text(json.dumps(manifest,indent=2));archive=R.parent/(R.name+'_REVIEW.tar.gz')
with tarfile.open(archive,'w:gz') as t:
 for p in members+[R/'MANIFEST.json']:t.add(p,arcname=R.name+'/'+str(p.relative_to(R)))
(R/'DELIVERY_STATUS.json').write_text(json.dumps(dict(state='PASS_LIMITED_16_SERVICE_REVIEW_READY',members=len(members),archive=str(archive),bytes=archive.stat().st_size,sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),full_steps_1_7=False),indent=2))

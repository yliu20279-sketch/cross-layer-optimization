import os,time,json,subprocess,signal,hashlib,tarfile,re
from pathlib import Path
R=Path(__file__).resolve().parent;V=R.parent/'swe_qwen3_legosim_16_service_20261030_v2';C=R.parent/'swe_qwen3_legosim_clock_fix_20261030_v1'
deadline=time.monotonic()+1800
while not (V/'DELIVERY_STATUS.json').exists() and time.monotonic()<deadline:time.sleep(10)
assert (V/'DELIVERY_STATUS.json').exists(),'clock prerequisite wait expired'
assert json.loads((V/'CLOCK_AUDIT.json').read_text())['state']=='PASS_LIMITED_16_NODE_CLOCK_BINDING_CORRECTED'
assert json.loads((V/'INDEPENDENT_AUDIT.json').read_text())['state']=='PASS_LIMITED_16_REAL_GATE_HOST_PCIE_HB_NOC_TWO_ROUND'
assert json.loads((V/'DELIVERY_STATUS.json').read_text())['state']=='PASS_LIMITED_16_SERVICE_REVIEW_READY'
assert all(hashlib.sha256((R/n).read_bytes()).hexdigest()==h for n,h in json.loads((R/'FREEZE.json').read_text()).items())
W=R/'run1';W.mkdir(exist_ok=False);env=dict(os.environ,SIMULATOR_ROOT='/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO',SWE_REQUIRE_NONEMPTY_DELAY='1',SWE_DOMAIN_SERVICES='1',SWE_CANONICAL_XY='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
start=time.time();reason=None
with (R/'RUN.log').open('w') as f:
 p=subprocess.Popen([str(C/'build/interchiplet'),str(R/'unified_full.yml'),'-t','2','-e','0','-w','4','-H','13','-f','4'],cwd=W,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 while p.poll() is None:
  bad=next((int(v) for v in re.findall(r'terminate with status = (\d+)',(R/'RUN.log').read_text()) if int(v)),None)
  if bad is not None or time.time()-start>10800:
   reason=('child_failure_'+str(bad)) if bad is not None else 'bounded_10800s_timeout';os.killpg(p.pid,signal.SIGTERM);break
  time.sleep(5)
 rc=p.wait(timeout=30)
(R/'RUN_EXIT.json').write_text(json.dumps(dict(returncode=rc,reason=reason,elapsed_seconds=time.time()-start),indent=2));print('FULL_EXIT',rc,reason,flush=True)
if rc or reason:raise SystemExit(2)
c=subprocess.run(['python3',str(R/'audit_clock.py')],capture_output=True,text=True);(R/'AUDIT.log').write_text(c.stdout+c.stderr);print(c.stdout,c.stderr,flush=True)
if c.returncode:raise SystemExit(c.returncode)
members=[p for p in sorted(R.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.stat().st_size<40*2**20]
manifest=[dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in members]
(R/'MANIFEST.json').write_text(json.dumps(manifest,indent=2));pack=R.parent/(R.name+'_REVIEW.tar.gz')
with tarfile.open(pack,'w:gz') as t:
 for p in members+[R/'MANIFEST.json']:t.add(p,arcname=R.name+'/'+str(p.relative_to(R)))
(R/'DELIVERY_STATUS.json').write_text(json.dumps(dict(state='PASS_LIMITED_16_LAYERS_REVIEW_READY',members=len(members),archive=str(pack),bytes=pack.stat().st_size,sha256=hashlib.sha256(pack.read_bytes()).hexdigest(),full_steps_1_7=False),indent=2))

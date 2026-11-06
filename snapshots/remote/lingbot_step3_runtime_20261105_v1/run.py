import os,pathlib,json,subprocess,signal,time,re,traceback,tarfile,hashlib
R=pathlib.Path(__file__).resolve().parent;B=R.parent;os.umask(0o022)
def put(n,v):(R/n).write_text(json.dumps(v,indent=2))
try:
 with (R/'BUILD.log').open('w') as f:c=subprocess.run([os.sys.executable,str(R/'prepare.py')],stdout=f,stderr=subprocess.STDOUT,timeout=300)
 assert c.returncode==0;W=R/'run';W.mkdir();env=dict(os.environ,SIMULATOR_ROOT='/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO',SWE_DOMAIN_SERVICES='1',SWE_CANONICAL_XY='1',SWE_REQUIRE_NONEMPTY_DELAY='1',OMP_NUM_THREADS='1')
 with (R/'RUN.log').open('w') as f:
  p=subprocess.Popen([str(B/'swe_qwen3_legosim_clock_fix_20261030_v1/build/interchiplet'),str(R/'config.yml'),'-t','2','-e','0','-w','4','-H','13','-f','4'],cwd=W,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);put('LAUNCH.json',dict(pid=p.pid,timeout_seconds=600));t=time.time()
  while p.poll() is None:
   if re.search(r'terminate with status = [1-9]',(R/'RUN.log').read_text()) or time.time()-t>600:
    os.killpg(p.pid,signal.SIGTERM);put('STOP_REASON.json',dict(timeout=time.time()-t>600,child_failure=True));break
   time.sleep(3)
  rc=p.wait(timeout=15)
 put('EXIT.json',dict(returncode=rc,wall_seconds=time.time()-t));assert rc==0 and not (R/'STOP_REASON.json').exists()
 with (R/'AUDIT.log').open('w') as f:c=subprocess.run([os.sys.executable,str(R/'audit.py')],stdout=f,stderr=subprocess.STDOUT,timeout=60)
 assert c.returncode==0;put('STATUS.json',dict(state='PASS_LIMITED_DUAL_CFG_K_SERVICE',whole_step5=False))
except BaseException:
 put('FAILURE.json',dict(error=traceback.format_exc()));put('STATUS.json',dict(state='STOPPED_FAILURE_PRESERVED',whole_step5=False));raise
finally:
 files=[q for q in sorted(R.rglob('*')) if q.is_file() and 'run' not in q.relative_to(R).parts and '__pycache__' not in q.parts and q.name not in ['review.tar.gz','MANIFEST.json','DELIVERY.json'] and q.stat().st_size<16*2**20];manifest=[]
 for q in files:q.chmod(0o644);manifest.append(dict(file=str(q.relative_to(R)),bytes=q.stat().st_size,sha256=hashlib.sha256(q.read_bytes()).hexdigest()))
 put('MANIFEST.json',manifest)
 with tarfile.open(R/'review.tar.gz','w:gz') as t:
  for q in files+[R/'MANIFEST.json']:t.add(q,arcname=str(q.relative_to(R)))
 put('DELIVERY.json',dict(sha256=hashlib.sha256((R/'review.tar.gz').read_bytes()).hexdigest(),bytes=(R/'review.tar.gz').stat().st_size,payloads=len(files)))

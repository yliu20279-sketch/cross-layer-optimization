import pathlib,json,subprocess,time,os,signal,re,traceback
R=pathlib.Path(__file__).resolve().parent;B=R.parent;os.umask(0o022)
def put(n,v):(R/n).write_text(json.dumps(v,indent=2))
try:
 with (R/'BUILD.log').open('w') as f:c=subprocess.run([os.sys.executable,str(R/'prepare.py')],stdout=f,stderr=subprocess.STDOUT,timeout=480)
 assert c.returncode==0
 W=R/'run';W.mkdir(exist_ok=False);env=dict(os.environ,SIMULATOR_ROOT='/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO',SWE_REQUIRE_NONEMPTY_DELAY='1',SWE_DOMAIN_SERVICES='1',SWE_CANONICAL_XY='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1');controller=B/'swe_qwen3_legosim_clock_fix_20261030_v1/build/interchiplet'
 with (R/'RUN.log').open('w') as f:
  p=subprocess.Popen([str(controller),str(R/'config.yml'),'-t','2','-e','0','-w','4','-H','13','-f','4'],cwd=W,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);start=time.time();put('LAUNCH.json',dict(pid=p.pid,timeout_seconds=86400,CPU_threads_per_rank=1,ranks=16))
  while p.poll() is None:
   bad=next((int(v) for v in re.findall(r'terminate with status = (\d+)',(R/'RUN.log').read_text()) if int(v)),None)
   failures=list(R.glob('case*/N*/FAILURE.json'))
   if bad or failures or time.time()-start>86400:
    os.killpg(p.pid,signal.SIGTERM);put('STOP_REASON.json',dict(child_status=bad,failures=list(map(str,failures)),timeout=time.time()-start>86400));break
   put('PROGRESS.json',dict(state='RUNNING_FULL_TP',elapsed_seconds=time.time()-start,passed_ranks=len(list(R.glob('case*/N*/PASS.json')))));time.sleep(5)
  rc=p.wait(timeout=30)
 put('RUN_EXIT.json',dict(returncode=rc,seconds=time.time()-start));assert rc==0 and not (R/'STOP_REASON.json').exists()
 with (R/'AUDIT.log').open('w') as f:c=subprocess.run([os.sys.executable,str(R/'audit.py')],stdout=f,stderr=subprocess.STDOUT,timeout=1800)
 assert c.returncode==0
 put('STATUS.json',dict(state='PASS_LIMITED_FULL_TP_CHECKPOINT_COMPOSITION',whole_step5=False))
except BaseException:
 put('FAILURE.json',dict(error=traceback.format_exc()));put('STATUS.json',dict(state='STOPPED_FAILURE_PRESERVED',whole_step5=False));raise

import pathlib,subprocess,json,os,shutil,time,hashlib,sqlite3,tarfile,traceback,signal
R=pathlib.Path(__file__).resolve().parent;B=R.parent;S=pathlib.Path('/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/snipersim');os.umask(0o022)
def put(n,v):(R/n).write_text(json.dumps(v,indent=2))
def bounded(cmd,stdout,timeout,env=None):
 p=subprocess.Popen(cmd,stdout=stdout,stderr=subprocess.STDOUT,env=env,start_new_session=True)
 try:return p.wait(timeout=timeout)
 except subprocess.TimeoutExpired:
  os.killpg(p.pid,signal.SIGTERM)
  try:p.wait(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
  raise

try:
 assert all(hashlib.sha256((R/n).read_bytes()).hexdigest()==h for n,h in json.loads((R/'FREEZE.json').read_text()).items())
 with (R/'prepare.log').open('w') as f:rc=bounded([os.sys.executable,str(R/'prepare.py')],f,180)
 assert rc==0
 for mode in ['native_data','sniper_data']:
  d=R/mode;d.mkdir(exist_ok=False)
  for q in R.glob('*.bin'):shutil.copy2(q,d/q.name)
 c=subprocess.run([str(R/'kernel'),str(R/'native_data')],capture_output=True,text=True,timeout=30);(R/'native.log').write_text(c.stdout+c.stderr);assert c.returncode==0 and (R/'native_data/FUNCTIONAL_PASS.json').exists()
 d=R/'sniper';d.mkdir(exist_ok=False);cmd=[str(S/'run-sniper'),'-n','4','-c','gainestown','-c',str(B/'swe_qwen3_host_boundary_20261027_v1/cpu_overlay.cfg'),'--roi','--no-cache-warming','-s','markers:stats','-d',str(d),'--',str(R/'kernel'),str(R/'sniper_data')];put('COMMAND.json',dict(args=cmd,Sniper_limit_seconds=240,CPU_active_threads=1,target_GPU_count=0))
 env=dict(os.environ,SIMULATOR_ROOT='/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO');start=time.time()
 with (R/'sniper.log').open('w') as f:rc=bounded(cmd,f,240,env)
 put('EXIT.json',dict(returncode=rc,wall_seconds=time.time()-start));assert rc==0 and (R/'sniper_data/FUNCTIONAL_PASS.json').exists()
 text=(R/'sniper.log').read_text();assert '*ERROR*' not in text and 'Assertion' not in text
 for name,N in [('K',128),('V',128),('Ocarry',2048)]:
  assert (R/'sniper_data'/(name+'_actual_F32.bin')).read_bytes()==(R/(name+'_F32_reference.bin')).read_bytes();assert (R/'sniper_data'/(name+'_actual_BF16.bin')).read_bytes()==(R/(name+'_GPU.bin')).read_bytes()
 db=sqlite3.connect(str(d/'sim.stats.sqlite3'));metrics=[]
 for i,label in enumerate(['K','V','Ocarry']):
  for a,b,phase in [(100+10*i,101+10*i,'decode'),(101+10*i,102+10*i,'FDA_software'),(102+10*i,103+10*i,'encode_bias')]:
   names=('marker-%d-0'%a,'marker-%d-0'%b);rows=list(db.execute("select p.prefixname,n.objectname,n.metricname,v.value from [values] v join prefixes p using(prefixid) join names n using(nameid) where v.core=0 and p.prefixname in (?,?)",names));values={}
   for prefix,obj,metric,value in rows:values.setdefault(obj+'.'+metric,{})[prefix]=value
   deltas={k:val[names[1]]-val[names[0]] for k,val in values.items() if names[0] in val and names[1] in val};assert deltas['performance_model.elapsed_time']>0;metrics.append(dict(label=label,phase=phase,marker_begin=a,marker_end=b,delta=deltas))
 put('INDEPENDENT_AUDIT.json',dict(state='PASS_LIMITED_ACTUAL_SNIPER_PORTABLE_FDA_KERNELS',FP32_elements=2304,BF16_GPU_elements=2304,bit_mismatches=0,marker_segments=metrics,cache_maintenance_requested=False,host_disk_and_initial_placement_cost_included=False,full_layer_cost=False,target_GPU_count=0,precision='BF16 original data + FP32 accumulator, integer emulation, no FP64 model math',scope='one real query K/V head0 and final Ocarry head15, portable baseline CPU software, no whole-operator generalization'))
 put('STATUS.json',dict(state='PASS_LIMITED_CPU_SOFTWARE_COST_PROBE',whole_step5=False))
except BaseException:
 put('FAILURE.json',dict(error=traceback.format_exc()));put('STATUS.json',dict(state='STOPPED_FAILURE_PRESERVED',whole_step5=False));raise
finally:
 files=[q for q in sorted(R.rglob('*')) if q.is_file() and q.name not in ['review.tar.gz','MANIFEST.json','DELIVERY.json'] and '__pycache__' not in q.parts and q.stat().st_size<16*2**20];manifest=[]
 for q in files:q.chmod(0o644);manifest.append(dict(file=str(q.relative_to(R)),bytes=q.stat().st_size,sha256=hashlib.sha256(q.read_bytes()).hexdigest()))
 put('MANIFEST.json',manifest)
 with tarfile.open(R/'review.tar.gz','w:gz') as t:
  for q in files+[R/'MANIFEST.json']:t.add(q,arcname=str(q.relative_to(R)))
 put('DELIVERY.json',dict(sha256=hashlib.sha256((R/'review.tar.gz').read_bytes()).hexdigest(),bytes=(R/'review.tar.gz').stat().st_size,payloads=len(files)))

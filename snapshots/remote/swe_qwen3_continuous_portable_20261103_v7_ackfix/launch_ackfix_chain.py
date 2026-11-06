import json,hashlib,time,subprocess,os,re,traceback
from pathlib import Path
B=Path.cwd();R=B/'swe_qwen3_continuous_portable_20261103_v7_ackfix';V=B/'swe_qwen3_lifetime_owned_20261103_v8_ackfix'
def put(p,x):p.write_text(json.dumps(x,indent=2))
try:
 deadline=time.monotonic()+1200
 while not (R/'ACKFIX_READY.json').exists():
  if time.monotonic()>deadline:raise TimeoutError('v7 preparation')
  time.sleep(5)
 assert not (R/'run1').exists()
 p=R/'collect_stream.py';s=p.read_text()
 assert "'sniper_isa_candidate' not in p.parts" in s
 p.write_text(s.replace("'sniper_isa_candidate' not in p.parts","'sniper_atomic' not in p.parts"))
 frozen=json.loads((R/'WORKER_FREEZE.json').read_text())
 frozen[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
 put(R/'WORKER_FREEZE.json',frozen)
 frozen['WORKER_FREEZE.json']=hashlib.sha256((R/'WORKER_FREEZE.json').read_bytes()).hexdigest()
 put(R/'FREEZE.json',frozen)
 put(R/'ADDITIONAL_AUDITOR_FREEZE.json',{n:frozen[n] for n in ['audit_cache_stream.py','snapshot_cpu_stats.py','collect_stream.py','watch_cache_live.py']})
 for name in ['watch_cache_live.py','audit_cache_stream.py']:
  s=(R/name).read_text()
  pattern=re.search(r"r'([^']*MAINT_WRITE_ACK[^']*)'",s)[1]
  assert re.search(pattern,'MAINT_WRITE_ACK 36169087 93824992902784 4624275465616480 4624275530621362\n')
  assert not re.search(pattern,'MAINT_WRITE_ACK 36169087 93824992902784 4624275465616480 4624275[RESPONSE]\n')
 subprocess.run(['python3','-B',str(R/'prepare_v8_ackfix.py')],check=True)
 def spawn(d,name):
  with (d/(name+'.log')).open('x') as f:
   return subprocess.Popen(['nice','-n','10','python3','-B',str(d/name)],cwd=d,stdout=f,stderr=subprocess.STDOUT,start_new_session=True).pid
 put(R/'STATUS.json',dict(state='LAUNCHING_NOT_PASS',full_steps_1_7=False))
 jobs={n:spawn(R,n) for n in ['supervise.py','audit_raw_when_ready.py','snapshot_cpu_stats.py','watch_cache_live.py','collect_stream.py']}
 put(R/'BACKGROUND_JOBS.json',jobs)
 put(R/'ACKFIX_CHAIN_STATUS.json',dict(state='V7_LAUNCHED_V8_GATE_ARMED',jobs=jobs,v8_gate_pid=spawn(V,'queue_after_v7.py')))
except Exception:
 (R/'ACKFIX_CHAIN_FAILURE.txt').write_text(traceback.format_exc())
 raise


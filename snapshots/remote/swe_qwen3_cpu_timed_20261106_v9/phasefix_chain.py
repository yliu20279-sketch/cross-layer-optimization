import json,subprocess,hashlib,time,traceback,os
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent
V=B/'swe_qwen3_lifetime_owned_20261103_v8_ackfix'
A=B/'swe_qwen3_continuous_portable_20261103_v7_ackfix'
py=B/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
def j(p):return json.loads(p.read_text())
def put(p,x):p.write_text(json.dumps(x,indent=2))
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(8388608):h.update(b)
 return h.hexdigest()
def run(name,interpreter,timeout):
 with (R/(name+'.log')).open('x') as f:
  subprocess.run([str(interpreter),'-B',str(R/name)],cwd=R,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=timeout)
try:
 put(R/'PHASEFIX_STATUS.json',dict(state='CPU_CONTROL_RUNNING_NOT_NATIVE',started=time.time()))
 run('control_replay.py',py,1800)
 run('audit_owned.py',py,600)
 assert j(R/'OWNED_CONTROL_AUDIT.json')['state']=='PASS_LIMITED_CPU_TWO_LAYER_KV_OWNERSHIP'
 nodes=j(R/'control_replay/NODES.json');plan=j(R/'LIFETIME_PLAN.json')
 regenerated=[{k:n[k] for k in ['id','label','shape','dtype','phase','layer']}|dict(readers=len(n['readers'])) for n in nodes]
 assert regenerated==plan and len(plan)==3920
 put(R/'OBSERVED_PLAN_AUDIT.json',dict(state='PASS_3920_OBSERVED_NODES_AND_READERS',plan_sha256=sha(R/'LIFETIME_PLAN.json')))
 assert j(A/'SAFE_DELIVERY_STATUS.json')['state']=='PASS_LIMITED_FULL_FUNCTIONAL_CPU_FP32_SRAM_SAFE_REVIEW'
 assert j(A/'CACHE_CHAIN_AUDIT.json')['state']=='PASS_LIMITED_FULL_TWO_LAYER_CACHE_AND_ALIAS_CHAIN'
 assert j(A/'RAW_ORACLE_AUDIT.json')['state']=='PASS_LIMITED_759_FP32_MATRICES_AND_56_STAGES_TWO_ROUND'
 # Recheck every external frozen dependency before starting the native experiment.
 for n,h in j(R/'EXTERNAL_DEPENDENCIES.json').items():assert sha(Path(n))==h,n
 original=j(V/'FREEZE.json');original.pop('WORKER_FREEZE.json')
 for n in ['PHASE_SWITCH_REGRESSION.json','PLAN_DIFF.json','OBSERVED_PLAN_AUDIT.json','replay_backend.py','control_replay.py','libcpu_probe.so','phasefix_chain.py']:
  original[n]=''
 hashes={n:sha(R/n) for n in original}
 put(R/'WORKER_FREEZE.json',hashes)
 hashes['WORKER_FREEZE.json']=sha(R/'WORKER_FREEZE.json')
 put(R/'FREEZE.json',hashes)
 put(R/'ADDITIONAL_AUDITOR_FREEZE.json',{n:hashes[n] for n in j(V/'ADDITIONAL_AUDITOR_FREEZE.json')})
 assert not (R/'run1').exists() and not (R/'RUN_PID.json').exists()
 jobs={}
 for name in ['supervise.py','audit_raw_when_ready.py','snapshot_cpu_stats.py','watch_cache_live.py','collect_stream.py']:
  with (R/(name+'.log')).open('x') as f:
   p=subprocess.Popen(['nice','-n','10','python3','-B',str(R/name)],cwd=R,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  jobs[name]=p.pid
 put(R/'BACKGROUND_JOBS.json',jobs)
 put(R/'PHASEFIX_STATUS.json',dict(state='NATIVE_TWO_ROUNDS_LAUNCHED_NOT_PASS',started=time.time(),jobs=jobs,CPU_control='PASS',bound_seconds=129600,full_steps_1_7=False))
except Exception:
 (R/'PHASEFIX_CHAIN_FAILURE.txt').write_text(traceback.format_exc())
 raise


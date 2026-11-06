import time,json,hashlib,os,signal,traceback
from pathlib import Path
R=Path(__file__).resolve().parent;deadline=time.monotonic()+89600;results=[]
try:
 while not (R/'oracle_cpu/RAW_MATRIX_ORACLE.json').exists():
  if time.monotonic()>deadline:raise TimeoutError('CPU oracle wait expired')
  time.sleep(5)
 oracle=json.loads((R/'oracle_cpu/RAW_MATRIX_ORACLE.json').read_text());assert len(oracle)==759
 for iteration in [1,2]:
  D=R/('case%d'%iteration)
  while not (D/'NODES.json').exists() or not (D/'MATRIX_CALLS.json').exists():
   if (R/'RUN_EXIT.json').exists() and json.loads((R/'RUN_EXIT.json').read_text())['returncode']!=0:raise RuntimeError('target run failed before raw audit')
   if time.monotonic()>deadline:raise TimeoutError('target matrix wait expired')
   time.sleep(10)
  nodes=json.loads((D/'NODES.json').read_text());raw=[v for v in nodes if v['label'] in ['lowered_GEMM_FP32','remote_GEMM_FP32']];calls=json.loads((D/'MATRIX_CALLS.json').read_text());assert len(raw)==len(calls)==len(oracle)==759
  for i,(v,c,g) in enumerate(zip(raw,calls,oracle)):
   assert [c[k] for k in ['M','N','K']]==[g[k] for k in ['M','N','K']],('shape',i)
   assert v['sha256']==g['output_sha256'],('FP32_first_difference',i,g['phase'],g['layer'],g['M'],g['N'],g['K'],v['sha256'],g['output_sha256'])
  files=json.loads((D/'FILES.json').read_text());assert len(files)==56
  for v in files:assert hashlib.sha256((D/v['path']).read_bytes()).hexdigest()==hashlib.sha256((R/'oracle_cpu'/v['path']).read_bytes()).hexdigest()
  results.append(dict(round=iteration,FP32_matrix_outputs_exact=759,elements=sum(v['M']*v['N'] for v in oracle),stage_files_exact=56))
  (R/'RAW_ORACLE_PROGRESS.json').write_text(json.dumps(results,indent=2))
 out=dict(state='PASS_LIMITED_759_FP32_MATRICES_AND_56_STAGES_TWO_ROUND',rounds=results,CPU_only_oracle=True,new_GPU_runs=0,full_steps_1_7=False);(R/'RAW_ORACLE_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out),flush=True)
except Exception:
 (R/'RAW_ORACLE_FAILURE.txt').write_text(traceback.format_exc())
 # An additional strict gate may stop only this experiment's verified process group.
 if (R/'RUN_PID.json').exists():
  pid=json.loads((R/'RUN_PID.json').read_text())['pid']
  try:
   cmd=Path('/proc/%d/cmdline'%pid).read_bytes()
   if os.getpgid(pid)==pid and str(R/'unified_full.yml').encode() in cmd:os.killpg(pid,signal.SIGTERM)
  except ProcessLookupError:pass
 raise

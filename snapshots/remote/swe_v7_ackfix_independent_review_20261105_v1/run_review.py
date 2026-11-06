from pathlib import Path
import subprocess,json,time,hashlib,traceback
R=Path(__file__).resolve().parent;SOURCE=R.parent/'swe_qwen3_continuous_portable_20261103_v7_ackfix'
start=time.monotonic();deadline=start+1800
try:
 for name in ['audit_clock.py','audit_cache_stream.py']:
  with (R/(name+'.log')).open('w') as log:
   p=subprocess.run(['nice','-n','10','python3',str(R/name)],cwd=R,stdout=log,stderr=subprocess.STDOUT,timeout=max(1,deadline-time.monotonic()))
   if p.returncode:raise RuntimeError((name,p.returncode))
 oracle=json.loads((SOURCE/'oracle_cpu/RAW_MATRIX_ORACLE.json').read_text())
 results=[]
 for iteration in [1,2]:
  d=SOURCE/f'case{iteration}';nodes=json.loads((d/'NODES.json').read_text())
  raw=[n for n in nodes if n['label'] in ['lowered_GEMM_FP32','remote_GEMM_FP32']]
  calls=json.loads((d/'MATRIX_CALLS.json').read_text())
  assert len(raw)==len(calls)==len(oracle)==759
  for index,(n,c,g) in enumerate(zip(raw,calls,oracle)):
   assert [c[k] for k in ['M','N','K']]==[g[k] for k in ['M','N','K']]
   assert n['sha256']==g['output_sha256'],index
  files=json.loads((d/'FILES.json').read_text());assert len(files)==56
  for n in files:
   assert hashlib.sha256((d/n['path']).read_bytes()).digest()==hashlib.sha256((SOURCE/'oracle_cpu'/n['path']).read_bytes()).digest()
  results.append(dict(round=iteration,FP32_matrices=759,FP32_elements=sum(g['M']*g['N'] for g in oracle),stages=56))
 (R/'RAW_ORACLE_RECHECK.json').write_text(json.dumps(results,indent=2))
 cache=json.loads((R/'CACHE_CHAIN_AUDIT.json').read_text())
 original=json.loads((SOURCE/'CACHE_CHAIN_AUDIT.json').read_text())
 for a,b in zip(cache['rounds'],original['rounds']):
  for key in ['raw_CPU_log_sha256','directory_write_acks','CPU_cache_gates','CPU_transport_clock_checks','ledger_sha256']:assert a[key]==b[key],key
 (R/'FINAL_REVIEW.json').write_text(json.dumps(dict(state='PASS_LIMITED_INDEPENDENT_FULL_TWO_LAYER_ISA_CACHE_CLOCK',source=str(SOURCE),elapsed_seconds=time.monotonic()-start,formal_matrix_runs=0,full_target_timing=False),indent=2))
except Exception:
 (R/'REVIEW_FAILURE.txt').write_text(traceback.format_exc())
 (R/'FINAL_REVIEW.json').write_text(json.dumps(dict(state='FAIL_INDEPENDENT_REVIEW',elapsed_seconds=time.monotonic()-start)))
 raise

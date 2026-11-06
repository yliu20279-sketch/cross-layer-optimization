import pathlib,json,time,subprocess,os
P=pathlib.Path(__file__).resolve().parent;D=P/'full_query_acceptance';start=time.time()
while time.time()-start<43320:
 if (D/'RESULT.json').exists():
  with (P/'all_query_audit.log').open('w') as f:r=subprocess.run(['/mnt/sda1/h3240101068/lingbot_steps1_2_20261027_v1/venv/bin/python',str(P/'audit_all_queries.py')],stdout=f,stderr=subprocess.STDOUT,timeout=600)
  (P/'ALL_QUERY_AUDIT_EXIT.json').write_text(json.dumps(dict(exit_code=r.returncode,target_GPU_count=0),indent=2));break
 if (D/'STATUS.json').exists():
  try:status=json.loads((D/'STATUS.json').read_text())
  except json.JSONDecodeError:time.sleep(1);continue
  if status.get('state','').startswith('STOPPED'):
   (P/'ALL_QUERY_AUDIT_EXIT.json').write_text(json.dumps(dict(status='NOT_RUN_NUMERICAL_GATE_FAILED_OR_BUDGET',numerical_status=status,target_GPU_count=0),indent=2));break
 time.sleep(15)
else:(P/'ALL_QUERY_AUDIT_EXIT.json').write_text(json.dumps(dict(status='NOT_RUN_WAIT_BUDGET',target_GPU_count=0)))

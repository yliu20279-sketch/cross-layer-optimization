import pathlib,subprocess,json,time,os,stat
P=pathlib.Path(__file__).resolve().parent;R=P/'full_layer_stagewise_v1';R.mkdir(exist_ok=True);py='/mnt/sda1/h3240101068/lingbot_steps1_2_20261027_v1/venv/bin/python';exits=[]
try:
 for script,budget,log in [('preflight_stagewise.py',240,'stagewise_preflight.log'),('stagewise_layer.py',43200,'stagewise_layer.log'),('audit_stagewise.py',1800,'stagewise_audit.log')]:
  with (P/log).open('w') as f:r=subprocess.run([py,str(P/script)],stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,timeout=budget)
  exits.append(dict(script=script,exit_code=r.returncode));(R/'EXITS.json').write_text(json.dumps(exits,indent=2))
  if r.returncode:
   status=json.loads((R/'STATUS.json').read_text()) if (R/'STATUS.json').exists() else {}
   if not status.get('state','').startswith('STOPPED'):(R/'STATUS.json').write_text(json.dumps(dict(state='STOPPED_CHILD_PROCESS_EXIT',script=script,exit_code=r.returncode,target_GPU_count=0),indent=2))
   raise SystemExit(r.returncode)
 for root,dirs,files in os.walk(R):
  os.chmod(root,0o755)
  for name in files:os.chmod(pathlib.Path(root)/name,0o644)
 (R/'PERMISSION_AUDIT.json').write_text(json.dumps(dict(status='PASS_POSIX_OTHER_READ_TRAVERSE',cross_account_login_test=False,target_GPU_count=0),indent=2))
except subprocess.TimeoutExpired as e:(R/'STATUS.json').write_text(json.dumps(dict(state='STOPPED_BUDGET_CHECKPOINTS_PRESERVED',script=e.cmd,target_GPU_count=0),indent=2));raise

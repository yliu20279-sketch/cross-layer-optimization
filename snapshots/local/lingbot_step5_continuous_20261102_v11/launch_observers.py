import pathlib,subprocess,sys,json,os
R=pathlib.Path(__file__).resolve().parent
assert (R/'KV_PREFLIGHT.json').exists() and (R/'LAUNCH.json').exists()
assert not (R/'OBSERVER_PIDS.json').exists()
pids={}
for n in ['watch_core.py','post_collect.py','sram_audit.py','feedback_audit.py','final_package.py','complete_collect.py']:
 args=[sys.executable,str(R/n)]
 if n in ['sram_audit.py','feedback_audit.py','complete_collect.py']:args.append(str(R))
 with (R/(n+'.log')).open('w') as f:p=subprocess.Popen(args,cwd=R,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 pids[n]=p.pid
(R/'OBSERVER_PIDS.json').write_text(json.dumps(pids,indent=2));print(json.dumps(pids))

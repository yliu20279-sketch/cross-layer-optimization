"""Read-only deduplication check for the lyc L1/L2 assignment."""
import json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent
script=r'''
import pathlib,subprocess,json,datetime
r=pathlib.Path('/mnt/sdb1/h4567/agent_cpu_npu_noc_20261113/formal_noc_20261118')
proc=subprocess.check_output(['ps','-eo','pid,ppid,user,etimes,args'],text=True)
out={'observed_at':datetime.datetime.now().astimezone().isoformat(),'relevant_processes':[x for x in proc.splitlines() if any(k in x.lower() for k in ['priority','run_matrix','formal_noc','synth_check','physical.tcl'])], 'directories':{}}
for root in [r,r.parent,pathlib.Path('/mnt/sdb1/h3240101068')]:
 out['directories'][str(root)]=[p.name for p in root.iterdir() if any(t in p.name.lower() for t in ['prior','l2','baseline','receipt','archive','status','result','audit','git'])]
for p in [r,r.parent]:
 q=subprocess.run(['git','-C',str(p),'rev-parse','--show-toplevel'],capture_output=True,text=True)
 out.setdefault('git_roots',{})[str(p)]=q.stdout.strip()
out['free']=subprocess.check_output(['free','-m'],text=True)
out['cpus']=subprocess.check_output(['nproc'],text=True).strip()
out['docker']=subprocess.check_output(['docker','ps','--format','{{.Names}} {{.Image}} {{.Status}}'],text=True)
print(json.dumps(out))
'''
p=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=12','myserver-113','python3','-'],input=script.encode(),capture_output=True,timeout=60)
if p.returncode:raise SystemExit(p.stderr.decode(errors='replace'))
d=json.loads(p.stdout);(R/'REMOTE_PREFLIGHT.json').write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(d,ensure_ascii=False,indent=2))

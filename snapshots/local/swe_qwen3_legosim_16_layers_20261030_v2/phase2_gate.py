import json,os,hashlib,shutil,subprocess,sys
from pathlib import Path
from check_case import check
R=Path(__file__).resolve().parent;round=int(os.environ['SWE_RUN_ROUND']);D=R/('case%d'%round);run=Path.cwd().parent
v=check(R,round);(D/'PRE_PHASE2_GATE.json').write_text(json.dumps(v,indent=2))
for n in ['bench.txt','transport_bench.txt','domain_service_round%d.csv'%round,'noc_feedback_round%d.csv'%round]:shutil.copy2(run/n,D/n)
bench=(D/'bench.txt').read_text().splitlines();assert bench
assert all(0<=int(a)<=16 for s in bench for a in s.split()[2:4])
c=subprocess.run(sys.argv[1:]);assert c.returncode==0,c.returncode
for n in ['delayInfo.txt']:shutil.copy2(run/n,D/n)
shutil.copy2(Path.cwd()/'routing_xy.csv',D/'routing_xy.csv');assert len((D/'delayInfo.txt').read_text().splitlines())==len(bench)
(D/'PHASE2_PASS.json').write_text(json.dumps(dict(state='PASS_FULL_HORIZONTAL_REPLAY',records=len(bench),delay_sha256=hashlib.sha256((D/'delayInfo.txt').read_bytes()).hexdigest()),indent=2))

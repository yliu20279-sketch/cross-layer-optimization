import json,os,hashlib,shutil,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/('case'+os.environ['SWE_RUN_ROUND']);run=Path.cwd().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
try:
 cases=json.loads((R/'CASES.json').read_text());assert len(cases)==16
 assert json.loads((D/'CPU_PASS.json').read_text())['state']=='PASS_16_REAL_BF16_GATE_PROJECTIONS'
 assert json.loads((D/'GATEWAY_PASS.json').read_text())['state']=='PASS_GATEWAY_16_PAYLOADS'
 for c in cases:
  rank=c['rank'];p=D/('N%02d'%rank);v=json.loads((p/'RESULT.json').read_text())
  assert v['weight_sha256']==v['HB_weight_sha256']==c['weight_sha256'] and v['input_sha256']==c['input_sha256']
  assert sha(p/'actual.bin')==c['gold_sha256'] and (D/('N%d_CPU_ACTUAL.bin'%rank)).read_bytes()==(p/'actual.bin').read_bytes()
  assert v['weight_last_reader']<=v['compute_done']<=v['returned']
 for n in ['bench.txt','transport_bench.txt','domain_service_round'+os.environ['SWE_RUN_ROUND']+'.csv','noc_feedback_round'+os.environ['SWE_RUN_ROUND']+'.csv']:shutil.copy2(run/n,D/n)
 bench=(D/'bench.txt').read_text().splitlines();assert bench
 for line in bench:
  v=line.split();assert 0<=int(v[2])<=16 and 0<=int(v[3])<=16
 (D/'PRE_PHASE2_GATE.json').write_text(json.dumps(dict(state='PASS_16_REAL_GATE_OUTPUTS_AND_CPU_RECEIPTS',outputs=16,bench_records=len(bench)),indent=2))
except Exception as e:
 (D/'GATE_FAILURE.json').write_text(json.dumps(dict(error=repr(e))));raise
c=subprocess.run(sys.argv[1:]);assert c.returncode==0,c.returncode
shutil.copy2(Path.cwd()/'routing_xy.csv',D/'routing_xy.csv')
delay=run/'delayInfo.txt';assert len(delay.read_text().splitlines())==len(bench);shutil.copy2(delay,D/'delayInfo.txt')
(D/'PHASE2_PASS.json').write_text(json.dumps(dict(state='PASS_FULL_HORIZONTAL_POPNET_REPLAY',records=len(bench),delay_sha256=sha(delay)),indent=2))

import json,csv,re,collections,hashlib
from pathlib import Path
H=Path(__file__).resolve().parent;R=H/'review'/H.name
def j(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert all(sha(R/n)==h for n,h in j(R/'FREEZE.json').items())
cases=j(R/'CASES.json');assert len(cases)==16
for round in [1,2]:
 D=R/('case%d'%round);assert j(D/'CPU_PASS.json')['state']=='PASS_16_REAL_BF16_GATE_PROJECTIONS'
 for c in cases:
  rank=c['rank'];N=D/('N%02d'%rank);v=j(N/'RESULT.json')
  assert v['rank']==rank and v['expert']==c['expert'] and v['token']==c['token']
  assert v['weight_sha256']==v['HB_weight_sha256']==c['weight_sha256']
  assert sha(N/'actual.bin')==c['gold_sha256'] and (N/'actual.bin').read_bytes()==(R/'data'/('N%02d_gold.bin'%rank)).read_bytes()==(D/('N%d_CPU_ACTUAL.bin'%rank)).read_bytes()
  assert v['weight_last_reader']<=v['compute_done']<=v['returned']
 bench=[list(map(int,s.split())) for s in (D/'bench.txt').read_text().splitlines()];delay=[list(map(int,s.split())) for s in (D/'delayInfo.txt').read_text().splitlines()]
 assert len(bench)==len(delay)==816
 assert collections.Counter((v[0],v[2],v[3],v[5]) for v in bench)==collections.Counter(tuple(v[:4]) for v in delay)
 feedback=list(csv.DictReader((D/('noc_feedback_round%d.csv'%round)).open()));assert len(feedback)==816 and all(int(v['profile_applied'])==round-1 for v in feedback)
 rows=list(csv.DictReader((D/('domain_service_round%d.csv'%round)).open()));assert collections.Counter(v['domain'] for v in rows)==dict(HB_RPC=4016,HOST_PCIE=816)
 assert len((D/'transport_bench.txt').read_text().splitlines())==5648
 routing=list(csv.DictReader((D/'routing_xy.csv').open()));assert len(routing)==289
 for v in routing:
  s,d,n=map(int,[v['source'],v['destination'],v['next_hop']]);target=0 if d==16 else d
  if s==d:e=s
  elif s==16:e=0
  elif d==16 and s==0:e=16
  elif s%4!=target%4:e=s+(1 if target%4>s%4 else -1)
  else:e=s+(4 if target//4>s//4 else -4)
  assert n==e
status=list(map(int,re.findall(r'terminate with status = (\d+)',(R/'RUN.log').read_text())));assert len(status)==70 and all(v==0 for v in status)
out=dict(state='PASS_LIMITED_LOCAL_16_SERVICE_REVIEW',members=371,unique_source_cases=16,rounds=2,BF16_output_elements_compared=24576,horizontal_records_each_round=816,HB_records_each_round=4016,PCIe_records_each_round=816,all_feedback_applied_round2=True,host_backing_file_bytes=j(R/'HOST_BACKING.json')['model_file_bytes'],host_backing_SHA_scope='all16 shards independently read on113, local review contains verification metadata only',full_steps_1_7=False)
(H/'LOCAL_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))

import json,csv,re,collections,hashlib
from pathlib import Path
from check_case import check
R=Path(__file__).resolve().parent
def j(p):return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(8*1024**2):h.update(b)
 return h.hexdigest()
assert all(sha(R/n)==h for n,h in j(R/'FREEZE.json').items())
assert all(sha(Path(n))==h for n,h in j(R/'EXTERNAL_DEPENDENCIES.json').items())
results=[];signatures=[]
for round in [1,2]:
 D=R/('case%d'%round);result=check(R,round);assert j(D/'PHASE2_PASS.json')['state']=='PASS_FULL_HORIZONTAL_REPLAY'
 bench=[list(map(int,s.split())) for s in (D/'bench.txt').read_text().splitlines()];delay=[list(map(int,s.split())) for s in (D/'delayInfo.txt').read_text().splitlines()]
 assert len(bench)==len(delay)>0
 assert collections.Counter((v[0],v[2],v[3],v[5]) for v in bench)==collections.Counter(tuple(v[:4]) for v in delay)
 assert all(v[4]==2 and 0<=v[5]<=v[6] for v in delay)
 feedback=list(csv.DictReader((D/('noc_feedback_round%d.csv'%round)).open()));assert len(feedback)==len(bench)
 assert all(int(v['profile_applied'])==(0 if round==1 else 1) for v in feedback)
 rows=list(csv.DictReader((D/('domain_service_round%d.csv'%round)).open()));transport=(D/'transport_bench.txt').read_text().splitlines();assert len(transport)==len(bench)+len(rows)
 assert {v['domain'] for v in rows}=={'HB_RPC','HOST_PCIE'}
 for v in rows:assert float(v['complete'])>=float(v['start'])>=float(v['ready'])
 for rank in range(16):
  txpath=(D if rank==0 else D/('N%02d'%rank))/('npusim_dram_transactions_%d_%d.csv'%(rank%4,rank//4));tx=list(csv.DictReader(txpath.open()));assert tx
  for v in tx:assert 0<=int(v['address']) and int(v['address'])+int(v['bytes'])<=512*2**20
  log=(R/'run1'/('proc_r%d_p1_t%d'%(round,3+2*rank))/('CH%02d.log'%rank)).read_text();assert 'size=536870912' in log and 'tx_bytes=32' in log
 route=list(csv.DictReader((D/'routing_xy.csv').open()));assert len(route)==289
 for v in route:
  s,d,n=map(int,[v['source'],v['destination'],v['next_hop']]);target=0 if d==16 else d
  expected=s if s==d else 0 if s==16 else 16 if d==16 and s==0 else s+(1 if target%4>s%4 else -1) if s%4!=target%4 else s+(4 if target//4>s//4 else -4)
  assert n==expected
 pair=collections.defaultdict(list)
 for v in bench:pair[(v[2],v[3])].append((v[4],v[5]))
 signatures.append(dict(pair));result.update(horizontal_records=len(bench),domain_records=len(rows),all_transport_records=len(transport));results.append(result)
assert signatures[0]==signatures[1]
log=(R/'RUN.log').read_text();statuses=list(map(int,re.findall(r'terminate with status = (\d+)',log)));assert len(statuses)==70 and all(v==0 for v in statuses)
assert 'Delay information is canncelled' not in log
out=dict(state='PASS_LIMITED_FULL_TWO_LAYER_16NPU_HOST_PCIE_TWO_ROUND',cases=results,original_BF16=True,host_GiB=128,HB_GiB=8,target_GPU_runs=0,full_opcode_and_CPU_service_timing=False,SRAM_Bank_timing=False,full_steps_1_7=False,scope='complete two-layer actual source outputs and16-NPU owner mapping with real host weights/PCIe/HB/NoC; generic compute proxies and missing software/Bank costs prevent complete target timing or benefit claims')
(R/'BASE_INDEPENDENT_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))

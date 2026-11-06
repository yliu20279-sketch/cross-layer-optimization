import json,csv,re,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent
def j(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert all(sha(R/n)==h for n,h in j(R/'FREEZE.json').items())
assert all(sha(Path(n))==h for n,h in j(R/'EXTERNAL_DEPENDENCIES.json').items())
back=j(R/'HOST_BACKING.json');assert len(back['shards'])==16 and back['reserved_model_extent']+back['pinned_windows_bytes']+back['extra_control_budget']<=128*2**30
cases=j(R/'CASES.json');assert len(cases)==16 and {c['rank'] for c in cases}==set(range(16))
rounds=[]
for round in [1,2]:
 D=R/('case%d'%round);assert j(D/'CPU_PASS.json')['state']=='PASS_16_REAL_BF16_GATE_PROJECTIONS'
 assert j(D/'CPU_PASS.json')['host_mapped_model_bytes']==back['model_file_bytes']
 assert j(D/'PRE_PHASE2_GATE.json')['outputs']==16 and j(D/'PHASE2_PASS.json')['records']==816
 tx_count=0
 for c in cases:
  rank=c['rank'];N=D/('N%02d'%rank);v=j(N/'RESULT.json');assert v['weight_sha256']==v['HB_weight_sha256']==c['weight_sha256'] and sha(N/'actual.bin')==c['gold_sha256']
  assert (D/('N%d_CPU_ACTUAL.bin'%rank)).read_bytes()==(N/'actual.bin').read_bytes()
  assert v['weight_last_reader']<=v['compute_done']<=v['returned']
  tx=list(csv.DictReader((N/('npusim_dram_transactions_%d_%d.csv'%(rank%4,rank//4))).open()));tx_count+=len(tx)
  assert len(tx)==100
  for t in tx:assert 0<=int(t['address']) and int(t['address'])+int(t['bytes'])<=512*2**20 and int(t['bytes'])<=65536
  weights=[t for t in tx if 65536<=int(t['address'])<65536+c['weight_bytes']]
  for op in ['STORE','LOAD']:assert sum(int(t['bytes']) for t in weights if t['operation']==op)==c['weight_bytes']
  log=(R/'run1'/('proc_r%d_p1_t%d'%(round,3+2*rank))/'CH%02d.log'%rank).read_text()
  assert 'size=536870912' in log and 'tx_bytes=32' in log
 rows=list(csv.DictReader((D/('domain_service_round%d.csv'%round)).open()));HB=[v for v in rows if v['domain']=='HB_RPC'];PCIE=[v for v in rows if v['domain']=='HOST_PCIE']
 feedback=list(csv.DictReader((D/('noc_feedback_round%d.csv'%round)).open()));assert len(feedback)==816
 assert all(int(v['profile_applied'])==(0 if round==1 else 1) for v in feedback)
 assert len(PCIE)==816 and len(HB)==4016
 assert sum(int(v['bytes']) for v in PCIE)==50422784
 assert sum(int(v['bytes']) for v in HB)==100908032
 for v in rows:assert float(v['complete'])>=float(v['start'])>=float(v['ready'])
 bench=(D/'bench.txt').read_text().splitlines();delay=(D/'delayInfo.txt').read_text().splitlines();assert len(bench)==len(delay)==816
 routing=list(csv.DictReader((D/'routing_xy.csv').open()));assert len(routing)==289
 for v in routing:
  s,d,n=map(int,[v['source'],v['destination'],v['next_hop']])
  if s==d:expected=s
  elif s==16:expected=0
  elif d==16 and s==0:expected=16
  else:
   target=0 if d==16 else d
   expected=s+(1 if target%4>s%4 else -1) if s%4!=target%4 else s+(4 if target//4>s//4 else -4)
  assert n==expected
 transport=(D/'transport_bench.txt').read_text().splitlines();assert len(transport)==len(bench)+len(rows)
 for line in bench:
  a=line.split();assert 0<=int(a[2])<=16 and 0<=int(a[3])<=16
 rounds.append(dict(round=round,outputs=16,BF16_elements=16*768,client_transactions=tx_count,horizontal_records=len(bench),HB_records=len(HB),PCIe_records=len(PCIE),all_transport_records=len(transport)))
log=(R/'RUN.log').read_text();statuses=list(map(int,re.findall(r'terminate with status = (\d+)',log)));assert len(statuses)==70 and all(x==0 for x in statuses)
assert 'Load 816 delay records.' in log
assert 'Delay information is canncelled' not in log
out=dict(state='PASS_LIMITED_16_REAL_GATE_HOST_PCIE_HB_NOC_TWO_ROUND',rounds=rounds,host_GiB=128,HB_GiB=8,NPU_count=16,CPU_ROIs=2,original_BF16=True,GPU_runs=0,physical_NPU_runs=0,full_layers_distributed=False,full_opcode_CPU_service_timing=False,full_steps_1_7=False,scope='16 actual selected expert gate projections and all real weight/payload paths; per-component research service proxies; not full distributed layers, complete CPU fallback/SRAM-bank timing or physical performance')
(R/'INDEPENDENT_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))

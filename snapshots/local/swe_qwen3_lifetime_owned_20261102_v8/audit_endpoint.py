import json,re,csv,sqlite3,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;P=R/'endpoint_positive';N=R/'endpoint_negative'
j=lambda p:json.loads(p.read_text())
assert j(P/'RUN_EXIT.json')['returncode']==0
statuses=list(map(int,re.findall(r'terminate with status = (\d+)',(P/'RUN.log').read_text())))
assert len(statuses)==10 and not any(statuses)
results=[]
for round in [1,2]:
 D=P/('case'+str(round));assert j(D/'CPU_TEARDOWN_PASS.json')['state']=='PASS_EMPTY_ARENA_ACK'
 assert j(D/'ENDPOINT_ROOT_PASS.json')['teardown_ack']
 assert j(D/'CPU_PASS.json')['state']=='PASS_ENDPOINT_SMOKE_ONLY'
 assert j(D/'GATEWAY_PASS.json')['state']=='PASS_ENDPOINT_GATEWAY_SMOKE'
 for phase in ['prefill','decode']:assert (D/(phase+'_CPU_ACTUAL.bin')).read_bytes()==bytes(range(32))
 services=[json.loads(s) for s in (D/'CPU_SERVICE_COMPLETIONS.jsonl').read_text().splitlines()]
 assert [s['kind'] for s in services][-3:]==[28,26,29]
 log=(P/'run1'/('proc_r%d_p1_t0'%round)/'cpu.log').read_text()
 assert 'ISA_NEHALEM_REJECTED' not in log and 'teardown with live ownership' not in log
 issued=0;ack=set();lastdone=0;drains=0;clocks=0
 for line in log.splitlines():
  m=re.search(r'MAINT_WRITE_ACK (\d+) (\d+) (\d+) (\d+)',line)
  if m:
   token,address,start,end=map(int,m.groups());assert token not in ack and end>=start;ack.add(token)
  m=re.search(r'MAINT_DRAIN (\d+) (\d+) (\d+) (\d+)',line)
  if m:
   issued,pending,now,done=map(int,m.groups());assert pending==0 and done>=now and len(ack)==issued and (not ack or max(ack)==issued);lastdone=done;drains+=1
  m=re.search(r'\[INTERCMD\] (?:READ|WRITE) (\d+) ',line)
  if m:assert int(m.group(1))*400000>=lastdone;clocks+=1
 assert drains>0 and clocks>0
 feedback=list(csv.DictReader((P/'run1'/('noc_feedback_round%d.csv'%round)).open()))
 assert feedback and (round==1 or all(int(v['profile_applied'])==1 for v in feedback))
 results.append(dict(round=round,cache_drains=drains,CPU_transport_clock_checks=clocks,ack_count=len(ack),feedback_records=len(feedback)))
db=sqlite3.connect(str(P/'sniper/sim.stats.sqlite3'))
rows=db.execute("select n.objectname,n.metricname,v.value from [values] v join names n using(nameid) join prefixes p using(prefixid) where p.prefixname='roi-end' and v.core=0 and n.objectname in ('decoded_isa_nehalem_ok','decoded_isa_nehalem_rejected')").fetchall();db.close()
assert rows and not any(v for o,n,v in rows if o=='decoded_isa_nehalem_rejected')
assert sum(v for o,n,v in rows if o=='decoded_isa_nehalem_ok')>0
assert j(N/'RUN_EXIT.json')['reason'].startswith('child_failure')
assert 'teardown with live ownership' in (N/'run1/proc_r1_p1_t0/cpu.log').read_text()
assert not (N/'case1/CPU_TEARDOWN_PASS.json').exists() and not (N/'case1/ENDPOINT_ROOT_PASS.json').exists()
out=dict(state='PASS_LIMITED_NATIVE_ENDPOINT_TEARDOWN',rounds=results,child_statuses=statuses,leaked_owner_refused=True,ISA_scope='both CPU logs contain no rejected instruction; final round SQLite independently zero rejected',scope='one active NPU/HB; 32-byte echo and cleanup only; not model/full16/cost acceptance',full_steps_1_7=False)
(R/'ENDPOINT_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))

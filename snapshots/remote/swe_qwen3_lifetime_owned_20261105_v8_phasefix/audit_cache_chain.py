import json,re,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;results=[]
for iteration in [1,2]:
 D=R/('case%d'%iteration);log=R/'run1'/('proc_r%d_p1_t0'%iteration)/'cpu.log'
 acks={};drains=[];last_done=0;clock_checks=0
 for line in log.read_text().splitlines():
  assert '*ERROR*' not in line and 'Assertion' not in line,('CPU_failure',iteration,line)
  m=re.search(r'MAINT_WRITE_ACK (\d+) (\d+) (\d+) (\d+)',line)
  if m:
   token,address,start,end=map(int,m.groups());assert token not in acks and end>=start;acks[token]=(address,start,end)
  m=re.search(r'MAINT_DRAIN (\d+) (\d+) (\d+) (\d+)',line)
  if m:
   issued,pending,now,done=map(int,m.groups());assert pending==0 and done>=now
   assert len([k for k in acks if k<=issued])==issued
   assert all(v[2]<=done for k,v in acks.items() if k<=issued)
   drains.append(dict(issued=issued,now_fs=now,done_fs=done,wait_fs=done-now));last_done=done
  m=re.search(r'\[INTERCMD\] (?:READ|WRITE) (\d+) ',line)
  if m:
   ticks=int(m.group(1));assert ticks*400000>=last_done,('cache_gate_before_CPU_transport',iteration,ticks,last_done);clock_checks+=1
 gates=[json.loads(s) for s in (D/'CPU_CACHE_GATES.jsonl').read_text().splitlines()]
 assert len(gates)==len(drains)>0 and clock_checks>0 and acks
 assert [v['sequence'] for v in gates]==list(range(1,len(gates)+1))
 assert all(v['completed'] and v['bytes']>0 and v['kind'] in ['before_send','before_receive','after_receive'] for v in gates)
 assert not json.loads((D/'LAYOUT_GAPS.json').read_text())
 results.append(dict(round=iteration,CPU_cache_gates=len(gates),directory_write_acks=len(acks),CPU_transport_clock_checks=clock_checks,wait_fs=sum(v['wait_fs'] for v in drains),max_wait_fs=max(v['wait_fs'] for v in drains),layout_gaps=0))
out=dict(state='PASS_LIMITED_FULL_TWO_LAYER_CACHE_AND_ALIAS_CHAIN',rounds=results,clock_period_fs=400000,scope='actual CPU0 software LRU maintenance, tracked directory DRAM writes and next CPU transport not early; frozen hierarchy only',full_target_timing=False,dynamic_reclamation=False,full_steps_1_7=False)
(R/'CACHE_CHAIN_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))

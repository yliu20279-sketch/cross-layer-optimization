"""Single-pass bounded-memory audit of all actual directory acknowledgments."""
import json,re,hashlib,csv,sqlite3
from pathlib import Path
R=Path(__file__).resolve().parent;results=[]
from cache_records import records
for iteration in [1,2]:
 D=R/('case%d'%iteration);log=R/'run1'/('proc_r%d_p1_t0'%iteration)/'cpu.log'
 db=sqlite3.connect(str(D/'CPU_FINAL_STATS.sqlite3'))
 values=db.execute("select v.value from [values] v join names n using(nameid) join prefixes p using(prefixid) where n.objectname='performance_model' and n.metricname='elapsed_time' and v.core=0 and p.prefixname='roi-end'").fetchall();assert len(values)==1;final_cpu_fs=values[0][0]
 isa_rows=db.execute("select n.objectname,n.metricname,v.value from [values] v join names n using(nameid) join prefixes p using(prefixid) where p.prefixname='roi-end' and v.core=0 and n.objectname in ('decoded_isa_nehalem_ok','decoded_isa_nehalem_rejected')").fetchall();db.close()
 assert isa_rows and not any(v for o,n,v in isa_rows if o=='decoded_isa_nehalem_rejected')
 isa_supported=sum(v for o,n,v in isa_rows if o=='decoded_isa_nehalem_ok');assert isa_supported>0
 prefix=0;out_of_order=set();maximum_ack_done=0;ack_count=0;drain_count=0;clock_count=0;last_done=0;wait_sum=0;wait_max=0;hash_log=hashlib.sha256();waiting=[]
 gates=(json.loads(s) for s in (D/'CPU_CACHE_GATES.jsonl').open())
 with (D/'CPU_CACHE_LEDGER.csv').open('w',newline='') as out:
  columns=['sequence','kind','bytes','address','issued','ack_prefix','ack_count','max_ack_done_fs','now_fs','done_fs','next_CPU_transport_ticks','final_CPU_elapsed_fs'];writer=csv.DictWriter(out,fieldnames=columns);writer.writeheader()
  def settle(ticks):
   for row in waiting:assert ticks*400000>=row['done_fs'];row['next_CPU_transport_ticks']=ticks;writer.writerow(row)
   waiting.clear()
  for raw,line in records(iteration):
   hash_log.update(raw);line=raw.decode('utf-8',errors='replace');
   if line.startswith('MAINT_WRITE_ACK '):assert re.fullmatch(r'MAINT_WRITE_ACK (\d+) (\d+) (\d+) (\d+)\n',line)
   if line.startswith('MAINT_DRAIN '):assert re.fullmatch(r'MAINT_DRAIN (\d+) (\d+) (\d+) (\d+)\n',line)
   assert '*ERROR*' not in line and 'Assertion' not in line,('CPU_failure',iteration,line[:160])
   m=re.fullmatch(r'MAINT_WRITE_ACK (\d+) (\d+) (\d+) (\d+)\n',line)
   if m:
    token,address,start,end=map(int,m.groups());assert token>prefix and token not in out_of_order and end>=start
    out_of_order.add(token);ack_count+=1;maximum_ack_done=max(maximum_ack_done,end)
    while prefix+1 in out_of_order:prefix+=1;out_of_order.remove(prefix)
   m=re.fullmatch(r'MAINT_DRAIN (\d+) (\d+) (\d+) (\d+)\n',line)
   if m:
    issued,pending,now,done=map(int,m.groups());assert pending==0 and done>=now and prefix>=issued and not out_of_order and maximum_ack_done<=done
    gate=next(gates);drain_count+=1;assert gate['sequence']==drain_count and gate['completed'] and gate['bytes']>0
    assert gate['kind'] in ['before_send','before_receive','after_receive'];wait_sum+=done-now;wait_max=max(wait_max,done-now);last_done=done
    waiting.append(dict(sequence=drain_count,kind=gate['kind'],bytes=gate['bytes'],address=gate['address'],issued=issued,ack_prefix=prefix,ack_count=ack_count,max_ack_done_fs=maximum_ack_done,now_fs=now,done_fs=done,next_CPU_transport_ticks=-1,final_CPU_elapsed_fs=final_cpu_fs))
   m=re.search(r'\[INTERCMD\] (?:READ|WRITE) (\d+) ',line)
   if m:
    ticks=int(m.group(1));assert ticks*400000>=last_done;clock_count+=1;settle(ticks)
  for row in waiting:assert final_cpu_fs>=row['done_fs'];writer.writerow(row)
 assert next(gates,None) is None and prefix==ack_count and not out_of_order and drain_count>0 and ack_count>0 and clock_count>0
 assert not json.loads((D/'LAYOUT_GAPS.json').read_text())
 results.append(dict(round=iteration,CPU_cache_gates=drain_count,ISA_nehalem_rejected=0,ISA_supported_decoded_occurrences=isa_supported,directory_write_acks=ack_count,CPU_transport_clock_checks=clock_count,wait_fs=wait_sum,max_wait_fs=wait_max,layout_gaps=0,final_CPU_elapsed_fs=final_cpu_fs,raw_CPU_log=str(log),raw_CPU_log_bytes=log.stat().st_size,merged_audit_stream_sha256=hash_log.hexdigest(),ledger_sha256=hashlib.sha256((D/'CPU_CACHE_LEDGER.csv').read_bytes()).hexdigest()))
a=R/'case1/CPU_CACHE_GATES.jsonl';b=R/'case2/CPU_CACHE_GATES.jsonl'
assert hashlib.sha256(a.read_bytes()).hexdigest()==hashlib.sha256(b.read_bytes()).hexdigest(),'two-round CPU cache address/input identity differs'
out=dict(state='PASS_LIMITED_FULL_TWO_LAYER_CACHE_AND_ALIAS_CHAIN',rounds=results,clock_period_fs=400000,CPU_address_identity=True,scope='all original ACK lines checked remotely in one pass; raw CPU logs retained on113; ledger is a compact derivative, not full raw log replay',full_target_timing=False,dynamic_reclamation=False,full_steps_1_7=False)
(R/'CACHE_CHAIN_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))

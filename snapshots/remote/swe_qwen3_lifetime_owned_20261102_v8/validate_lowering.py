import json,csv,hashlib,collections
from pathlib import Path
def validate(R,iteration):
 R=Path(R);D=R/('case%d'%iteration)
 def j(p):return json.loads(p.read_text())
 matrices=j(D/'MATRIX_CALLS.json');assert len(matrices)==759
 services=j(D/'CPU_SERVICES.json');cpu=[json.loads(s) for s in (D/'CPU_SERVICE_COMPLETIONS.jsonl').read_text().splitlines()];assert len(services)==len(cpu)>0
 for i,(v,c) in enumerate(zip(services,cpu)):
  assert v['id']==i+1 and all(v[k]==c[k] for k in ['kind','input_bytes','output_bytes']) and v['start']<=v['complete']
  if i:assert services[i-1]['complete']<=v['start']
 assert set(v['kind'] for v in services)>={1,2,3,4,5,6,7,8,9,11,12,13,14,15,16,17,18,19,20,21}
 all_lower=[];all_vectors=[]
 for rank in range(16):
  Q=D if rank==0 else D/('N%02d'%rank);low=[json.loads(s) for s in (Q/'LOWERING.jsonl').read_text().splitlines()];all_lower.extend((rank,v) for v in low)
  for v in low:assert v['mul_ops']==v['M']*v['N']*v['K'] and v['begin']<=v['last_reader']<=v['complete'] and v['events']==v['compute_cycles'] and v['bank_cycles']>0
  tiles=list(csv.reader((Q/'MATRIX_TILES.csv').open()));group=collections.defaultdict(list)
  for row in tiles:
   job,version,n0,start,ready,last,done=map(int,row);assert start<=ready<=last<=done;group[job].append((version,n0,start,ready,last,done))
  for v in low:
   ts=group[v['job']];assert len(ts)==v['weight_versions']==(v['N']+63)//64 and [t[0] for t in ts]==list(range(1,len(ts)+1))
   for a,b in zip(ts,ts[1:]):assert a[4]<=b[2]
  if rank==0:
   vectors=[json.loads(s) for s in (Q/'VECTOR_LOWERING.jsonl').read_text().splitlines()];assert vectors;all_vectors=vectors
   for v in vectors:assert v['begin']<=v['last_reader']<=v['complete'] and v['events']==(v['n']+15)//16
  expected=[m for m in matrices if m['owner']==rank];assert collections.Counter((v['M'],v['N'],v['K']) for v in low)==collections.Counter((v['M'],v['N'],v['K']) for v in expected)
 assert not j(D/'LAYOUT_GAPS.json')
 assert 22 in set(v['kind'] for v in services)
 assert len(all_lower)==759
 gates=[json.loads(line) for line in (D/'IMMEDIATE_FP32_GATES.jsonl').read_text().splitlines()];assert len(gates)==759 and all(v['exact'] for v in gates) and [v['sequence'] for v in gates]==list(range(1,760))
 io_count=0;io_cycles=0
 for rank in range(16):
  Q=D if rank==0 else D/('N%02d'%rank);io=list(csv.DictReader((Q/'IO_SRAM_GATES.csv').open()));assert io
  previous=0
  for v in io:
   n,start,done=map(int,[v['bytes'],v['start'],v['complete']]);assert 0<n<=65536 and previous<=start and done-start==(n+255)//256;previous=done;io_count+=1;io_cycles+=done-start
 big=[v for v in services if v['input_bytes']+v['output_bytes']+196608>4*2**20];assert big and all(v.get('streamed_HB') and v.get('max_staging_bytes')==65536 for v in big)
 root_tx=list(csv.DictReader((D/'npusim_dram_transactions_0_0.csv').open()));labels={v['label'] for v in root_tx};assert {'streamed_original_BF16_weight','BF16_weight_codec_actual_HB_reader','CPU_expanded_weight_streamed_HB'}<=labels

 nodes=j(D/'NODES.json')
 for node in nodes:
  assert node['offset']+node['bytes']<=240*2**20 and node['control_ready']<=node['commit']<=node['ready']
  service=node['prior_service_id'];assert 0<=service<=len(services)
  if service:assert services[service-1]['complete']<=node['control_ready']
 summary=dict(state='PASS_LIMITED_FULL_MATRIX_CPU_SOFTWARE_SRAM_FUNCTIONAL',round=iteration,matrix_calls=len(all_lower),shapes=len(set((v['M'],v['N'],v['K']) for _,v in all_lower)),vector_calls=len(all_vectors),CPU_software_calls=len(services),immediate_FP32_gates=len(gates),IO_SRAM_gates=io_count,IO_SRAM_cycles=io_cycles,CPU_service_kinds=sorted(set(v['kind'] for v in services)),native_matrix_compute_events=sum(v['events'] for _,v in all_lower),SRAM_bank_matrix_cycles=sum(v['bank_cycles'] for _,v in all_lower),layout_provenance_gaps=len(j(D/'LAYOUT_GAPS.json')),cache_maintenance_timing_certified=False,full_target_timing=False,full_steps_1_7=False)
 (D/'LOWERING_AUDIT.json').write_text(json.dumps(summary,indent=2));return summary

import json,hashlib,subprocess,sys,struct
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/(sys.argv[1] if len(sys.argv)>1 else 'control_replay');B=R.parent;reference=B/'swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1'
j=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
nodes=j(D/'NODES.json');events=j(D/'LIFETIME_EVENTS.json');plan=j(R/'LIFETIME_PLAN.json');assert len(nodes)==len(plan)
live={};reuses=0;live_bytes=0;peak=0
for event in events:
 if event['kind']=='allocate':
  i=event['node'];n=nodes[i];size=n['allocation_bytes'];assert n['offset']%32==0 and n['offset']>=32*2**20 and n['offset']+size<=240*2**20
  for v in live.values():assert n['offset']+size<=v['offset'] or v['offset']+v['allocation_bytes']<=n['offset'],('overlap_while_live',i,v['id'])
  for old in nodes[:i]:
   if old['offset']<n['offset']+size and n['offset']<old['offset']+old['allocation_bytes']:
    assert old['retired_at']<=n['control_ready'] and old['allocation_version']!=n['allocation_version'];reuses+=1
  live[i]=n;live_bytes+=size;peak=max(peak,live_bytes);assert live_bytes==event['live_bytes']
 elif event['kind']=='release_after_consumer_barrier':
  n=live.pop(event['node']);assert n['ready']<=n['last_consumer_barrier_start']<=n['retired_at']==event['complete']
  assert all(rd['done']<=n['last_consumer_barrier_start'] for rd in n['readers'])
  assert len(n['readers'])==n['planned_readers']==plan[n['id']]['readers'];live_bytes-=n['allocation_bytes']
assert not live and live_bytes==0 and reuses>0
services=j(D/'CPU_SERVICES.json');allocations=[s for s in services if s['kind']==24];reads=[s for s in services if s['kind']==25];barriers=[s for s in services if s['kind']==26]
ae=[e for e in events if e['kind']=='allocate'];re=[e for e in events if e['kind'] in ['zero_reader_commit','last_reader_progress']]
assert len(allocations)==len(ae)==len(nodes) and len(reads)==len(re) and len(barriers)==5
running_peak=0
for s,e in zip(allocations,ae):
 n=nodes[e['node']];running_peak=max(running_peak,e['live_bytes']);expected=struct.pack('<QQQQ',e['address'],e['version'],e['live_bytes'],running_peak)
 assert (s['a'],s['b'],s['c'])==(n['bytes'],n['id'],n['planned_readers']) and s['output_sha256']==hashlib.sha256(expected).hexdigest() and s['complete']<=n['control_ready']
for s,e in zip(reads,re):
 expected=struct.pack('<QQQQ',e['address'],e['version'],e['remaining'],0)
 assert (s['a'],s['b'],s['c'])==(e['node'],e['version'],int(e['kind']=='zero_reader_commit')) and s['output_sha256']==hashlib.sha256(expected).hexdigest() and s['complete']==e['complete']
batch=[];generation=0;peak_seen=0;barrier_index=0
for e in events:
 if e['kind']=='allocate':generation=max(generation,e['version']);peak_seen=max(peak_seen,e['live_bytes'])
 elif e['kind']=='release_after_consumer_barrier':batch.append((e['node'],e['version']))
 elif e['kind']=='barrier':
  s=barriers[barrier_index];barrier_index+=1;assert batch==sorted(batch) and len(batch)==e['released'] and len(batch)<=s['a']
  payload=bytearray(32+16*s['a']);struct.pack_into('<QQQQ',payload,0,len(batch),e['live_bytes'],peak_seen,generation)
  for k,(node,version) in enumerate(batch):struct.pack_into('<QQ',payload,32+16*k,node,version)
  assert s['output_sha256']==hashlib.sha256(payload).hexdigest() and (s['start'],s['complete'])==(e['start'],e['complete'])
  batch=[]
assert barrier_index==5 and not batch
assert [(v['phase'],v['layer']) for v in events if v['kind']=='barrier']==[('prefill',0),('prefill',1),('decode',0),('decode',1),('final_CPU_return',-1)]
files=j(D/'FILES.json');assert len(files)==56
for v in files:assert sha(D/v['path'])==sha(reference/v['path'])
g=[json.loads(s) for s in (D/'IMMEDIATE_FP32_GATES.jsonl').read_text().splitlines()];oracle=j(R/'oracle_cpu/RAW_MATRIX_ORACLE.json');assert len(g)==len(oracle)==759
for a,b in zip(g,oracle):assert a['exact'] and a['actual_sha256']==b['output_sha256'] and all(a[k]==b[k] for k in ['M','N','K'])
checks=[v for v in j(D/'CHECKS.json') if v['strict']];assert len(checks)==12 and all(v['exact'] and not v['different'] for v in checks)
assert not j(D/'LAYOUT_GAPS.json');assert j(R/'ALLOCATOR_CONTROLS.json')['state']=='PASS_LIMITED_C_ALLOCATOR_CONTROLS'
native=D.name in ['case1','case2'];assert not native or (D/'CPU_PASS.json').is_file()
out=dict(state='PASS_LIMITED_NATIVE_TWO_LAYER_LIFETIME_REUSE' if native else 'PASS_LIMITED_TWO_LAYER_CPU_LIFETIME_REUSE',nodes=len(nodes),CPU_managed_allocations=len(nodes),all_nodes_retired=True,overlapping_address_reuse_pairs=reuses,peak_live_aligned_bytes=peak,retained_all_aligned_bytes=sum(n['allocation_bytes'] for n in nodes),strict_stage_files=56,strict_output_KV_checks=12,raw_FP32_gates=759,scope='actual C allocation/refcount/reclaim and HB byte reuse; finite already-seen DAG; timing must be audited separately; no policy benefit',target_native_runs=int(native),new_GPU_runs=0,full_steps_1_7=False)
((D/'LIFETIME_AUDIT.json') if native else (R/'LIFETIME_CONTROL_AUDIT_V2.json')).write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))

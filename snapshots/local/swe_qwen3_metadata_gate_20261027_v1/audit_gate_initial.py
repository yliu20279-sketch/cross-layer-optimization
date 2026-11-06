"""Independent trace, ABI and release-order audit; no model/library execution."""
import gzip,hashlib,json,struct,sys
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent;D=R/'attempt1';B=R.parent;SOURCE=B/'swe_qwen3_softmax_top8_20261027_v1'
def read(p):return json.loads(p.read_text())
def ceildiv(a,b):return (a+b-1)//b
s=read(D/'STATUS.json');gate=read(D/'GATE_EVENTS.json');uploads=read(D/'UPLOADS.json');clocks=read(D/'CLOCKS.json')
ds=read(D/'LINK_DESCRIPTORS.json');packets=read(D/'LINK_PACKETS.json');mem=read(D/'HOST_DMA_MEMORY.json');windows=read(D/'WINDOWS.json')
events=[json.loads(x) for x in gzip.open(D/'events.jsonl.gz','rt')];arena=[json.loads(x) for x in gzip.open(D/'sram.jsonl.gz','rt')]
done={};prev=0;write=load=tx=0
for e in events:
 assert e['id'] not in done and e['start']>=prev and e['done']>=e['start']
 assert all(d in done and done[d]<=e['start'] for d in e['deps'])
 assert e['kind'] not in [2,3,4],'no arithmetic or fake TopK instructions in metadata fragment'
 if e['kind'] in [0,1]:
  sectors=set()
  for address,n in e['segments']:
   assert 0<=address<address+n<=60736;sectors.update(range(address//32,(address+n+31)//32))
  assert len(sectors)==e['requests'] and e['tx']==32 and sum(n for _,n in e['segments'])==e['bytes']
  tx+=e['requests']
  if e['kind']==0:load+=e['bytes']
  else:write+=e['bytes']
 done[e['id']]=e['done'];prev=e['done']
assert len(events)==8 and write==load==60720 and tx==3796
assert prev==s['native']['metadata_ready_proxy_ns']
for c in clocks:assert c['done_ns']==max(c['before_ns'],ceildiv(c['ready_fs'],1000000))
cpu=next(g for g in gate if g['event']=='CPU_route_complete');assert cpu['time_fs']>=3715344800000
source_id=(SOURCE/'attempt1/gold_IDs.bin').read_bytes();source_w=(SOURCE/'attempt1/gold_weights_BF16.bin').read_bytes()
blob=(D/'transferred_metadata.bin').read_bytes();assert blob==source_id+source_w and len(blob)==60720
plane={'IDs':source_id,'weights':source_w};link_free=0
for p in packets:
 assert p['start_fs']>=link_free
 assert p['serialize_done_fs']-p['start_fs']==ceildiv(p['bytes']*100000000,5504)
 assert p['arrival_fs']-p['serialize_done_fs']==250000000 and 0<p['bytes']<=256
 link_free=p['serialize_done_fs']
for d,u,m in zip(ds,uploads,mem):
 assert d['queue'] in range(4) and d['credit'] in range(16)
 assert m['ready_fs']>=cpu['time_fs'] and m['start_fs']>=m['ready_fs']
 assert m['done_fs']==m['start_fs']+60000000+ceildiv(m['bytes']*10000000,128)
 assert d['ready_fs']==m['done_fs'] and d['issue_fs']>=d['ready_fs']
 assert d['iommu_done_fs']==d['issue_fs']+20000000
 ps=[p for p in packets if p['descriptor']==d['id']]
 assert sum(p['bytes'] for p in ps)==d['bytes']==len(plane[u['plane']])
 assert ps[0]['start_fs']>=d['iommu_done_fs'] and d['arrival_fs']==ps[-1]['arrival_fs']
 assert d['sha256']==hashlib.sha256(plane[u['plane']]).hexdigest()
 assert u['commit_fs']==d['commit_fs']==done[u['native_event']]*1000000
 assert events[u['native_event']-1]['start']*1000000>=d['arrival_fs']
lease={}
for w in windows:
 if w['action']=='acquire':assert w['id'] not in lease;lease[w['id']]=w['bytes'];assert len(lease)<=2
 else:assert w['time_fs']>=w['hold_until'] and lease.pop(w['id'])==w['bytes']
assert not lease
committed=[g for g in gate if g['event']=='HB_plane_committed'];assert {g['plane'] for g in committed}=={'IDs','weights'}
sram=next(g for g in gate if g['event']=='metadata_SRAM_ready');release=next(g for g in gate if g['event']=='dispatch_descriptors_released')
read_event=next(e for e in events if e['label']=='metadata_HB_readback')
assert read_event['start']*1000000>=max(g['time_fs'] for g in committed)
assert sram['time_fs']>=sram['read_done_fs']==read_event['done']*1000000
assert release['time_fs']>=sram['time_fs']>=max(g['time_fs'] for g in committed)>=cpu['time_fs']
used=peak=0;live={}
for a in arena:
 if a['action']=='alloc':live[a['id']]=a['bytes'];used+=a['bytes'];peak=max(peak,used)
 else:assert a['cycle']*1000000>=release['time_fs'];used-=live.pop(a['id'])
assert not live and used==0 and peak==60720
contexts=read(D/'CONTEXTS.json');ids=np.frombuffer(source_id,dtype='<i8').reshape(759,8);weights=np.frombuffer(source_w,dtype='<u2').reshape(759,8)
expected_contexts=[]
for r in read(SOURCE/'attempt1/RESULTS.json')['rows']:
 for token in range(r['tokens']):expected_contexts.append(dict(root=r['root'],request=r['request'],phase=r['phase'],layer=0,local_token=token))
assert contexts==expected_contexts
records=list(struct.iter_unpack('<IIHBBBBHQQ',(D/'dispatch_descriptors_32B.bin').read_bytes()));assert len(records)==6072
owners=[0]*16;epoch_tag=int.from_bytes(hashlib.sha256(cpu['epoch'].encode()).digest()[:8],'little')
for index,(row,token,expert,slot,owner,origin,reserved,weight,input_ref,epoch) in enumerate(records):
 assert (row,slot)==divmod(index,8) and token==contexts[row]['local_token']
 assert expert==int(ids[row,slot]) and weight==int(weights[row,slot])
 assert owner==expert%16 and origin==token%16 and reserved==0 and input_ref==row*4096 and epoch==epoch_tag
 owners[owner]+=1
assert sum(owners)==6072 and s['softmax_FP32_GPU_difference'].startswith('FAILED_RETAINED')
assert len(s['negative_controls'])==13
for n,h in read(R/'FREEZE.json').items():assert hashlib.sha256((R/n).read_bytes()).hexdigest()==h
report=dict(state='PASS_LIMITED_METADATA_CAUSALITY_AND_DISPATCH_DESCRIPTOR_ABI',CPU_route_complete_fs=cpu['time_fs'],
 HB_last_commit_fs=max(g['time_fs'] for g in committed),metadata_SRAM_ready_fs=sram['time_fs'],dispatch_release_fs=release['time_fs'],
 events=len(events),DRAM32B_transactions=tx,metadata_bytes=60720,descriptors=len(ds),packets=len(packets),SRAM_peak_bytes=peak,dispatch_records=6072,owner_record_counts=owners,
 IDs_and_BF16_weights_preserved=True,source_slot_order_preserved=True,origin_reset_per_source_phase=True,negative_controls=13,
 scope='descriptor release after actual metadata callbacks only; input_ref is logical activation offset, not bound HB address; activation residency/NoC/expert execution not certified',
 softmax_FP32_difference='retained; no tolerance change')
out=Path(sys.argv[1]) if len(sys.argv)>1 else D/'INDEPENDENT_AUDIT.json'
out.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

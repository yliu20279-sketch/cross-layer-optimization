"""Independent byte/lifetime/clock audit; writes a separate path when requested."""
import gzip,hashlib,json,sys
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent;D=R/'coupled_attempt2';CPU=R/'attempt1'
def read(p):return json.loads(p.read_text())
def ceildiv(a,b):return (a+b-1)//b
s=read(D/'STATUS.json');desc=read(D/'LINK_DESCRIPTORS.json');pack=read(D/'LINK_PACKETS.json');leases=read(D/'PINNED_WINDOW_LIFETIMES.json')
dma=read(D/'HOST_DMA_MEMORY.json');arena=read(D/'HOST_ARENA.json');clock=read(D/'CLOCK_AND_UPLOAD.json')
events=[json.loads(x) for x in gzip.open(D/'events.jsonl.gz','rt')];sram=[json.loads(x) for x in gzip.open(D/'sram.jsonl.gz','rt')]
done={};prev=0;hbread=hbwrite=tx=ops=0
for e in events:
 assert e['id'] not in done and e['start']>=prev and e['done']>=e['start']
 assert all(d in done and done[d]<=e['start'] for d in e['deps'])
 assert e['kind']!=2
 if e['kind'] in [0,1]:
  sectors=set()
  for a,n in e['segments']:
   assert a>=0 and a+n<=536870912
   sectors.update(range(a//32,(a+n+31)//32))
  assert len(sectors)==e['requests'] and e['tx']==32 and sum(n for _,n in e['segments'])==e['bytes']
  tx+=e['requests']
  if e['kind']==0:hbread+=e['bytes']
  else:hbwrite+=e['bytes']
 elif e['kind']==3:ops+=e['ops']
 done[e['id']]=e['done'];prev=e['done']
assert hbread==1065472 and hbwrite==1057280 and tx==66336 and ops==524416
assert prev==s['device']['modeled_proxy_end_ns'] and len(events)==16689
live={};used=peak=0
for e in sram:
 if e['action']=='alloc':
  assert e['id'] not in live;live[e['id']]=e['bytes'];used+=e['bytes'];peak=max(peak,used)
 else:assert live.pop(e['id'])==e['bytes'];used-=e['bytes']
 assert used<=4194304
assert not live and used==0 and peak==17408
pfree={'H2D':0,'D2H':0};credits={};pack_by={}
for p in pack:
 assert 0<p['bytes']<=256 and p['start_fs']>=pfree[p['direction']]
 assert p['serialize_done_fs']-p['start_fs']==ceildiv(p['bytes']*100000000,5504)
 assert p['arrival_fs']-p['serialize_done_fs']==250000000
 pfree[p['direction']]=p['serialize_done_fs'];pack_by.setdefault(p['descriptor'],[]).append(p)
source=(CPU/'decode_result.bin').read_bytes();return_bytes=np.load(D/'new_router_FP32.npy').astype('<f4').tobytes()
for d in desc:
 assert d['queue'] in range(4) and d['credit'] in range(16) and 0<d['bytes']<=65536
 key=(d['queue'],d['credit']);assert d['issue_fs']>=max(d['ready_fs'],credits.get(key,0))
 assert d['iommu_done_fs']==d['issue_fs']+20000000
 ps=pack_by[d['id']];assert sum(p['bytes'] for p in ps)==d['bytes']
 assert ps[0]['start_fs']>=d['iommu_done_fs'] and d['arrival_fs']==ps[-1]['arrival_fs'] and d['commit_fs']>=d['arrival_fs']
 assert [p['offset'] for p in ps]==list(range(0,d['bytes'],256))
 credits[key]=d['commit_fs']
 if d['direction']=='H2D':
  u=next(u for u in clock['uploads'] if u['descriptor']==d['id']);offset=u['offset']+(8192 if u['label']=='uploaded_router_workspace' else 0)
  data=source[offset:offset+d['bytes']];assert u['commit_fs']==done[u['event']]*1000000==d['commit_fs']
 else:data=return_bytes
 assert hashlib.sha256(data).hexdigest()==d['sha256']
memfree=0
for m in dma:
 assert m['start_fs']>=max(memfree,m['ready_fs'])
 assert m['service_fs']==ceildiv(m['bytes']*10000000,128) and m['latency_fs']==60000000
 assert m['done_fs']==m['start_fs']+m['latency_fs']+m['service_fs'];memfree=m['done_fs']
reads=[m for m in dma if m['direction']=='DMA_host_read'];hd=[d for d in desc if d['direction']=='H2D']
assert len(reads)==len(hd)==17
assert all(m['done_fs']==d['ready_fs'] and m['bytes']==d['bytes'] for m,d in zip(reads,hd))
assert dma[-1]['direction']=='DMA_host_write' and dma[-1]['done_fs']<=clock['encode_start_ns']*1000000
assert clock['compute_start_ns']*1000000>=max(d['commit_fs'] for d in hd)
lease_live={};lease_peak=0
for e in leases:
 if e['action']=='acquire':
  assert e['id'] not in lease_live and e['bytes']<=65536;lease_live[e['id']]=e['bytes'];assert len(lease_live)<=2
  lease_peak=max(lease_peak,sum(lease_live.values()))
 else:assert e['time_fs']>=e['hold_until'] and lease_live.pop(e['id'])==e['bytes']
assert not lease_live and lease_peak==arena['window_lease_peak_bytes']==65536
active=peakhost=0
for e in arena['events']:
 active+=e['bytes'] if e['action'].startswith('allocate') else -e['bytes'];assert active>=0;peakhost=max(peakhost,active)
assert peakhost==arena['temporary_actual_peak_bytes']==1056768 and active==arena['retained_result_bytes']==256
assert arena['admission_reserved_bytes']<=arena['capacity_bytes']==128*2**30
raw={x['mode']:x for x in read(CPU/'SNIPER_RAW_METRICS.json')}
for k,v in clock['cpu'].items():
 r=raw[k]['stats'];assert v['ROI_elapsed_fs']==r['performance_model.elapsed_time'][0]==v['nonidle_fs']+v['idle_fs']
 assert raw[k]['resolved_config']['perf_model/core/frequency']=='2.5'
for c in clock['clock_events']:assert c['done_ns']==max(c['before_ns'],ceildiv(c['ready_fs'],1000000))
newbits=np.load(D/'new_router_BF16_bits.npy').astype('<u2').tobytes();assert newbits==(CPU/'gold_BF16.bin').read_bytes()==(CPU/'encode_result.bin').read_bytes()
assert return_bytes==(CPU/'output_FP32.bin').read_bytes()
report=dict(state='PASS_LIMITED_INDEPENDENT_HOST_NATIVE_CAUSALITY_BYTES_CAPACITY',events=len(events),transactions=tx,descriptors=len(desc),packets=len(pack),
 H2D_bytes=sum(d['bytes'] for d in hd),D2H_bytes=512,HB_read_bytes=hbread,HB_write_bytes=hbwrite,
 host_expanded_peak_bytes=peakhost,pinned_window_peak_bytes=lease_peak,SRAM_peak_bytes=peak,
 modeled_primary_proxy_ns=prev,numerical_bits_exact=True,
 sensitivity_scope='STATUS nonidle_only_sensitivity_ns is arithmetic idle subtraction, NOT a resimulation; DRAM refresh/alignment may change with absolute phase, excluded from promoted timing results',
 limits='proxy timing, no physical calibration, descriptor CPU preparation/polling/cache maintenance/gateway fixed propagation unmodeled')
out=Path(sys.argv[1]) if len(sys.argv)>1 else D/'INDEPENDENT_AUDIT.json'
out.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

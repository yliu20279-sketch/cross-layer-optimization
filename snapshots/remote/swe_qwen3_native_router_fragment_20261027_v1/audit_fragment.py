"""Independent delivered event/lifetime audit; no numeric payload recomputation."""
import gzip,hashlib,json,math
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/'attempt2'
s=json.loads((D/'STATUS.json').read_text());events=[json.loads(x) for x in gzip.open(D/'events.jsonl.gz','rt')]
arena=[json.loads(x) for x in gzip.open(D/'sram.jsonl.gz','rt')]
done={};prev=0;read=write=transactions=ops=0;checks=[]
for e in events:
 assert e['id'] not in done and e['start']>=prev and e['done']>=e['start']
 assert all(d in done and done[d]<=e['start'] for d in e['deps'])
 if e['kind'] in [0,1]:
  sectors=set()
  for address,n in e['segments']:
   assert address>=0 and address+n<=536870912
   sectors.update(range(address//32,(address+n+31)//32))
  assert len(sectors)==e['requests'] and e['tx']==32
  assert sum(n for _,n in e['segments'])==e['bytes']
  transactions+=e['requests']
  if e['kind']==0:read+=e['bytes']
  else:write+=e['bytes']
 elif e['kind']==3:ops+=e['ops']
 assert e['kind']!=2,'FP16/MAC shortcut forbidden'
 done[e['id']]=e['done'];prev=e['done']
live={};used=peak=0
for e in arena:
 if e['action']=='alloc':
  assert e['id'] not in live;live[e['id']]=e['bytes'];used+=e['bytes'];peak=max(peak,used);assert used<=4194304
 else:
  assert e['id'] in live and live.pop(e['id'])==e['bytes'];used-=e['bytes']
assert not live and used==0
c=s['device']['counts']
assert read==1065472 and write==512 and transactions==33312
assert ops==524416 and ops==c['vector_ops']
assert read==c['HB_read_bytes'] and write==c['HB_write_bytes'] and transactions==c['RAM_transactions']
assert peak==s['device']['SRAM_peak_bytes'] and prev==s['device']['fragment_proxy_cycles']
assert c['SRAM_service_bytes']==c['SRAM_read_bytes']+c['SRAM_write_bytes']==6326272
assert len(events)==c['events']
assert all(x['exact'] for x in s['checks']) and len(s['device']['negative_controls'])==4
report=dict(state='PASS_LIMITED_NATIVE_EVENT_DEPENDENCY_CAPACITY_BYTES',events=len(events),
 vector_ops=ops,MAC_ops=0,HB_read_bytes=read,HB_write_bytes=write,DRAM_32B_transactions=transactions,SRAM_peak_bytes=peak,
 device_fragment_proxy_cycles=prev,negative_controls=s['device']['negative_controls'],
 scope='independent trace/lifetime/byte audit; not target BF16 conversion, host-link or complete router timing certification')
(D/'INDEPENDENT_AUDIT.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))

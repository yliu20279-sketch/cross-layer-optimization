import gzip,hashlib,json,math,struct,sys
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/'attempt2'
def load(p):return json.loads(p.read_text())
def sha(b):return hashlib.sha256(b).hexdigest()
status=load(D/'STATUS.json');stats=load(D/'PE_STATS.json');com=load(D/'COMMUNICATIONS.json')
acts=load(D/'ACTIVATION_RESIDENCY.json');reuse=load(D/'LAST_READERS_AND_REUSE.json');accepted=load(D/'EXPERT_RECEIVES.json')
origin=load(D/'ORIGIN_METADATA_READY.json');raw=(D/'ACTIVATIONS_BF16.bin').read_bytes()
parent=R.parent/'swe_qwen3_metadata_gate_20261027_v1/attempt1'
meta=(parent/'transferred_metadata.bin').read_bytes();desc=(parent/'dispatch_descriptors_32B.bin').read_bytes()
for n,h in load(R/'FREEZE_v2.json').items():assert sha((R/n).read_bytes())==h,n
assert len(raw)==81920 and len(acts)==len(reuse)==20 and len(com)==175 and len(accepted)==160
events=[];arenas=[]
for rank in range(16):
 ev=[json.loads(l) for l in gzip.open(D/('N%02d'%rank)/'events.jsonl.gz','rt')];em={e['id']:e for e in ev};events.append(em)
 for e in ev:
  assert e['done']>=e['start'] and e['kind'] not in [2,3,4]
  for dep in e['deps']:assert dep in em and em[dep]['done']<=e['start']
 ar=[json.loads(l) for l in gzip.open(D/('N%02d'%rank)/'sram.jsonl.gz','rt')];arenas.append(ar)
 live={};peak=0
 for a in ar:
  if a['action']=='alloc':assert a['id'] not in live;live[a['id']]=a['bytes'];peak=max(peak,sum(live.values()))
  elif a['action']=='free':assert a['id'] in live;assert live.pop(a['id'])==a['bytes']
 assert not live and peak==stats[rank]['SRAM_peak_bytes'] and peak<=4194304
 for kind,key in [(0,'HB_read_bytes'),(1,'HB_write_bytes')]:assert sum(e['bytes'] for e in ev if e['kind']==kind)==stats[rank]['counts'][key]
 assert sum(e['requests'] for e in ev)==stats[rank]['counts']['RAM_transactions']
 for kind in ['metadata','token']:
  tx=[a for a in ar if a['action']=='alloc' and a.get('label')==('origin_metadata_TX' if kind=='metadata' else 'token_TX_snapshot')]
  cs=[c for c in com if c['kind']==kind and c['src']==rank]
  drains=[e for e in ev if e['label']==kind+'_TX_drain']
  assert len(tx)==len(cs)==len(drains)
  for a,c,e in zip(tx,cs,drains):
   frees=[z for z in ar if z['action']=='free' and z['id']==a['id']];assert len(frees)==1
   assert a['bytes']==c['bytes']==e['bytes'] and e['done']==c['source_ready'] and frees[0]['cycle']==c['TX_release']>=c['tail']
assert sum(s['counts']['HB_read_bytes'] for s in stats)==1396032
assert sum(s['counts']['HB_write_bytes'] for s in stats)==904512
assert sum(s['counts']['RAM_transactions'] for s in stats)==71892
packets=[tuple(map(float,l.split())) for l in (D/'packets.txt').read_text().splitlines()]
batches=load(D/'NOC_BATCHES.json');assert len(packets)==4850 and len(batches)==2
assert {int(p[0]) for p in packets}==set(range(4850))
for b in batches:
 ps=[p for p in packets if b['first']<=p[0]<b['last']]
 assert len(ps)==b['last']-b['first'] and all(p[3]>=p[2]>=b['earliest'] for p in ps)
 for i,(_,_,n) in enumerate(b['messages']):
  q=[p for p in ps if int(p[1])==i];assert len(q)==n//128 and math.ceil(max(p[3] for p in q))<=b['ends'][i]
cap=load(D/'noc_capacity.json');assert cap['peak_input_flits']<=8 and cap['peak_output_flits']<=8 and cap['NI_blocked_cycles']>0 and cap['per_cycle_checks']
for a,r in zip(acts,reuse):
 row=a['row'];rank=a['rank'];body=raw[row*4096:(row+1)*4096];em=events[rank]
 assert a['global_address']==(rank<<29)+a['local_address'] and a['source_hash']==sha(body)==r['old_hash']
 assert a['producer_ready']==em[a['producer_event']]['done']
 assert {v['slot'] for v in r['last_readers']}==set(range(8)) and len(r['last_readers'])==8
 for v in r['last_readers']:
  e=em[v['event']];assert e['kind']==0 and e['bytes']==4096 and e['segments']==[[a['local_address'],4096]]
  assert e['start']>=max(a['producer_ready'],origin[str(rank)]) and e['done']<=v['done_ns']<=r['retired_ns']
 assert r['retired_ns']<=r['overwrite_done']<=batches[1]['earliest'] and r['new_hash']==sha(b'\xa5'*4096)
for c in com:
 assert c['source_ready']<=c['tail']<=c['TX_release'] and c['tail']<=c['RX_HB_ready']<=c['receiver_visible']
 assert c['source_hash']==c['received_hash'] and c['receiver_region_global']==(c['dst']<<29)+c['receiver_region_local']
 e=events[c['dst']][c['receiver_read_event']];assert e['kind']==0 and e['start']>=c['RX_HB_ready'] and e['bytes']==c['bytes']
 if c['src']!=c['dst']:
  b=batches[c['native_batch']];i=c['native_message'];assert b['messages'][i]==[c['src'],c['dst'],c['bytes']] and b['ends'][i]==c['tail'] and b['earliest']>=c['source_ready']
 else:assert c['native_batch'] is None
 if c['kind']=='token':
  i=c['message'];row,slot=divmod(i,8);wire=(D/('receiver_%03d.bin'%i)).read_bytes();body=wire[128:];f=struct.unpack('<IIHBBBBHQQ',wire[:32])
  assert len(wire)==4224 and wire[:32]==desc[i*32:(i+1)*32] and body==raw[row*4096:(row+1)*4096]
  assert sha(wire)==c['received_hash'] and wire[64:96]==hashlib.sha256(body).digest()
  magic,src,dst,msg,n=struct.unpack('<8sIIQQ',wire[32:64]);assert magic.rstrip(b'\0')==b'SWETOK1' and (src,dst,msg,n)==(c['src'],c['dst'],i,4096)
  assert f[0]==row and f[3]==slot and f[4]==c['dst']==f[2]%16 and f[5]==c['src']
  assert c['source_ready']>=origin[str(c['src'])]
  v=accepted[i];assert v['body_hash']==sha(body) and v['weight_bits']==f[7] and not v['expert_execution_ready'] and v['receive_ready']==c['receiver_visible']
 else:
  ctx=load(D/'CONTEXTS.json');rank=c['dst'];rows=[i for i,v in enumerate(ctx) if v['local_token']%16==rank]
  epoch=struct.unpack('<IIHBBBBHQQ',desc[:32])[-1]
  frame=struct.pack('<8sIIQQ',b'SWEMETA',0,rank,epoch,len(rows))+b'\0'*96
  for row in rows:frame+=struct.pack('<II',row,ctx[row]['local_token'])+meta[row*64:(row+1)*64]+meta[48576+row*16:48576+(row+1)*16]+b'\0'*8
  frame+=b'\0'*((-len(frame))%128)
  assert sha(frame)==c['received_hash'] and len(frame)==c['bytes'] and origin[str(rank)]==c['receiver_visible']
assert len(set(status['negative_controls']))==len(status['negative_controls'])
source_verified=False
if '--verify-source' in sys.argv:
 import torch
 B=R.parent;fp=B/'swe_qwen3_step3_gpu_20261026_v1/requests/R0002/layer0_actual_fixtures.pt'
 manifest=load(fp.parent/'MANIFEST.json');assert sha(fp.read_bytes())==next(x['sha256'] for x in manifest if x['path']==fp.name)
 f=torch.load(fp,weights_only=True,map_location='cpu');v=torch.cat([f['prefill']['moe_input'],f['decode']['moe_input']],0).contiguous()
 assert v.dtype==torch.bfloat16 and v.view(torch.uint8).numpy().tobytes()==raw
 for path,x in load(D/'SOURCE_BINDING.json').items():assert sha(Path(path).read_bytes())==x['sha256']
 pm={x['path']:x for x in load(parent.parent/'FILE_MANIFEST.json')}
 for name in ['transferred_metadata.bin','dispatch_descriptors_32B.bin','CONTEXTS.json','INDEPENDENT_AUDIT.json']:
  assert sha((parent/name).read_bytes())==pm['attempt1/'+name]['sha256']
 source_verified=True
out=dict(state='PASS_LIMITED_INDEPENDENT_CAUSALITY_AND_PAYLOAD',source_fixture_and_binaries_verified=source_verified,tokens=20,assignments=160,NoC_packets=len(packets),negative_controls=len(status['negative_controls']),HB_read_bytes=1396032,HB_write_bytes=904512,RAM_transactions=71892,SRAM_peak_bytes=max(s['SRAM_peak_bytes'] for s in stats),HB_allocated_bytes=sum(s['HB_allocated_bytes'] for s in stats),NoC_capacity=cap,softmax_FP32='FAILED_RETAINED',physical_NPU_runs=0)
target=Path(next((s for s in sys.argv[1:] if not s.startswith('--')),str(D/'INDEPENDENT_AUDIT.json')))
target.write_text(json.dumps(out,indent=2));print(json.dumps(out))

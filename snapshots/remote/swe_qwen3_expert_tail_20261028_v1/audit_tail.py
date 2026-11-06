import gzip,hashlib,json,math,struct,sys
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/'native_attempt1'
def j(p):return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while x:=f.read(8*1024*1024):h.update(x)
 return h.hexdigest()
for freeze in ['FREEZE.json','CPU_FREEZE.json']:
 for n,h in j(R/freeze).items():assert sha(R/n)==h
s=j(D/'STATUS.json');assert len(s['checks'])==4 and all(v['exact'] and v['different']==0 for v in s['checks'])
c=j(R/'cpu_tail_attempt1/RESULTS.json');assert c['rows']==180 and not any(c['differences'].values())
c=j(R/'cpu_attempt1/SILU_CHECK.json');assert c['finite_BF16_values']==65280 and c['different']==c['real_gate_different']==0
events={};free={}
for rank in [0,1]:
 es=[json.loads(l) for l in gzip.open(D/('N%02d'%rank)/'events.jsonl.gz','rt')];em={e['id']:e for e in es};events[rank]=em
 for e in es:
  assert e['done']>=e['start'] and e['kind'] not in [2,4]
  for dep in e['deps']:assert em[dep]['done']<=e['start']
 ar=[json.loads(l) for l in gzip.open(D/('N%02d'%rank)/'sram.jsonl.gz','rt')];live={};peak=0;fr={}
 for a in ar:
  if a['action']=='alloc':assert a['id'] not in live;live[a['id']]=a['bytes'];peak=max(peak,sum(live.values()))
  else:assert live.pop(a['id'])==a['bytes'];fr[a['id']]=a['cycle']
 assert not live and peak==s['device'][str(rank)]['SRAM_peak_bytes']<=4194304;free[rank]=fr
 for kind,key in [(0,'HB_read_bytes'),(1,'HB_write_bytes')]:assert sum(e['bytes'] for e in es if e['kind']==kind)==s['device'][str(rank)]['counts'][key]
 assert sum(e['requests'] for e in es)==s['device'][str(rank)]['counts']['RAM_transactions']
assert s['device']['1']['counts']['vector_ops']==3406592
l=j(D/'LAST_READERS.json');regions={v['label']:v for v in l['regions']}
for label,r in regions.items():
 assert r['pending']==[] and r['retired_ns'] is not None
 readers=[x for x in l['readers'] if x['label']==label];assert readers and all(events[1][x['event']]['done']<=x['done_ns']<=r['retired_ns'] for x in readers)
 if label in ['down_input_FP32','down_weight_FP32']:assert len(readers)==32 and {v['reader'] for v in readers}=={'tile%d'%i for i in range(32)}
for a in l['SRAM']:
 assert events[1][a['last_event']]['done']==a['done_ns'] and all(free[1][b]>=a['done_ns'] for b in a['buffers'])
assert l['return_inbox_retained'] and l['return_inbox_pending']==['source_weighted_commit']
rs=j(D/'RESIDENCY.json')
for r in rs:assert r['global_address']==(1<<29)+r['local'] and r['ready_ns']==events[1][r['producer']]['done']
for i,a in enumerate(regions.values()):
 for b in list(regions.values())[i+1:]:assert a['local']+a['bytes']<=b['local'] or b['local']+b['bytes']<=a['local']
des=j(D/'LINK_DESCRIPTORS.json');dm={d['id']:d for d in des};pack=j(D/'LINK_PACKETS.json')
for d in des:
 ps=[p for p in pack if p['descriptor']==d['id']];assert sum(p['bytes'] for p in ps)==d['bytes'] and max(p['arrival_fs'] for p in ps)<=d['commit_fs']
for t in j(D/'TRANSFERS.json'):
 d=dm[t['descriptor']];e=events[1][t['event']];assert e['kind']==1 and e['bytes']==t['bytes']==d['bytes'] and e['start']*1000000>=d['arrival_fs'] and e['done']*1000000==d['commit_fs']
live={}
for a in j(D/'PINNED_LIFETIMES.json'):
 if a['action']=='acquire':assert len(live)<2;live[a['id']]=a
 else:assert a['id'] in live and a['time_fs']>=a['hold_until'];del live[a['id']]
assert not live
ret=j(D/'RETURN_DEPENDENCIES.json');ps=[tuple(map(float,v.split())) for v in (D/'packets.txt').read_text().splitlines()];batch=j(D/'NOC_BATCHES.json')[0]
assert len(ps)==33 and {int(p[0]) for p in ps}==set(range(33)) and all(p[1]==0 and p[3]>=p[2]>=ret['send_ready'] and p[3]<=ret['tail'] for p in ps)
assert batch['messages']==[[1,0,4224]] and batch['ends']==[ret['tail']]
assert ret['send_ready']>=s['down_done_ns'] and ret['tail']<=ret['TX_release'] and ret['tail']<=ret['HB_ready']<=ret['consumer_ready']
assert events[0][ret['consumer_event']]['start']>=ret['HB_ready'] and ret['weighted_commit'] is False
tx=next(a for a in [json.loads(l) for l in gzip.open(D/'N01/sram.jsonl.gz','rt')] if a['action']=='alloc' and a['label']=='return_TX_snapshot');assert free[1][tx['id']]==ret['TX_release']
drain=[e for e in events[1].values() if e['label']=='return_TX_drain'];assert len(drain)==1 and drain[0]['bytes']==4224 and drain[0]['done']==ret['send_ready']
wire=(D/'returned_frame.bin').read_bytes();assert len(wire)==4224 and hashlib.sha256(wire).hexdigest()==ret['sha256'] and wire[128:]==(D/'down_BF16.bin').read_bytes()==(D/'down_CPU_BF16.bin').read_bytes()
assert wire[:32].hex()==ret['metadata_descriptor'] and wire[64:96]==hashlib.sha256(wire[128:]).digest()
assert struct.unpack('<8sIIQQ',wire[32:64])==(b'SWERET1\0',1,0,0,4096)
fields=struct.unpack('<IIHBBBBHQQ',wire[:32]);assert fields[0]==0 and fields[2]==49 and fields[3]==0 and fields[4]==1 and fields[5]==0
cap=j(D/'noc_capacity.json');assert cap['peak_input_flits']<=8 and cap['peak_output_flits']<=8 and cap['per_cycle_checks']
source=False
if '--verify-source' in sys.argv:
 import numpy as np
 import torch
 torch.set_num_threads(1);model=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B');bindings=j(D/'WEIGHT_BINDING.json')['selected'];verified=set();weights={}
 for proj,b in bindings.items():
  p=model/b['shard']
  if p not in verified:assert sha(p)==b['verified_shard_sha256'];verified.add(p)
  with p.open('rb') as f:f.seek(b['file_offset']);blob=f.read(b['bytes'])
  assert hashlib.sha256(blob).hexdigest()==b['sha256'];weights[proj]=torch.from_numpy(np.frombuffer(blob,dtype='<u2').copy()).view(torch.bfloat16).reshape(b['shape'])
 parent=R.parent/'swe_qwen3_activation_noc_20261027_v1/attempt2';original=(parent/'receiver_000.bin').read_bytes();x=torch.from_numpy(np.frombuffer(original[128:],dtype='<u2').copy()).view(torch.bfloat16).reshape(1,2048)
 gate=torch.nn.functional.linear(x,weights['gate_proj']);up=torch.nn.functional.linear(x,weights['up_proj']);silu=torch.nn.functional.silu(gate);product=silu*up;down=torch.nn.functional.linear(product,weights['down_proj'])
 for name,value in [('silu',silu),('product',product),('down',down)]:assert value.view(torch.uint8).numpy().tobytes()==(D/(name+'_BF16.bin')).read_bytes()
 # Independent scalar libm SiLU expression at FP32 boundaries.
 g=gate.float().numpy().reshape(-1)
 exp_values=np.array([math.exp(float(-v)) for v in g],dtype='<f4')
 vals=np.divide(g,np.add(np.float32(1),exp_values,dtype=np.float32),dtype=np.float32)
 def rb(a):
  u=np.ascontiguousarray(a,dtype='<f4').view('<u4');return ((u+np.uint32(0x7fff)+((u>>16)&1))>>16).astype('<u2')
 assert rb(vals).tobytes()==(D/'silu_BF16.bin').read_bytes()
 xf=product.float().numpy().reshape(-1);w=weights['down_proj'].float().numpy();lanes=np.zeros((64,2048),dtype='<f4')
 for k in range(768):lanes[k%64]=np.add(lanes[k%64],xf[k]*w[:,k],dtype=np.float32)
 for off in [32,16,8,4,2,1]:lanes[:off]=np.add(lanes[:off],lanes[off:2*off],dtype=np.float32)
 assert lanes[0].tobytes()==(D/'down_FP32.bin').read_bytes() and rb(lanes[0]).tobytes()==(D/'down_BF16.bin').read_bytes()
 old=j(parent/'SOURCE_BINDING.json')
 for name in ['olmoearth_v3_6_integration_20261025_v1/run_integrated.py','olmoearth_v3_6_integration_20261025_v1/canonical_ram.yaml','olmoearth_v3_6_multi_npu_20261025_v1/libolmo_native_01.so','olmoearth_v3_6_multi_npu_20261025_v1/libolmo_native_00.so','olmoearth_v3_6_multi_npu_20261025_v1/noc_bridge_v2']:
  p=R.parent/name;assert sha(p)==old[str(p)]['sha256']
 source=True
out=dict(state='PASS_LIMITED_M1_TAIL_RETURN_AUDIT',source_weights_full_CPU_expert_and_independent_math_verified=source,events=sum(len(es) for es in events.values()),RAM_transactions=sum(v['counts']['RAM_transactions'] for v in s['device'].values()),vector_ops=3406592,SRAM_peak_bytes=max(v['SRAM_peak_bytes'] for v in s['device'].values()),negative_controls=len(s['negative_controls']),NoC_packets=33,NoC_capacity=cap,returned_BF16_elements=2048,weighted_commit=False,softmax_FP32='FAILED_RETAINED',batch='DIFFERENCES_RETAINED',physical_NPU_runs=0)
target=Path(next((x for x in sys.argv[1:] if not x.startswith('--')),str(D/'INDEPENDENT_AUDIT.json')));target.write_text(json.dumps(out,indent=2));print(json.dumps(out))

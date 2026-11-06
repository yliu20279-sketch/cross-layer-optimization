import gzip,hashlib,json,struct,sys,math
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/'native_attempt1'
def j(p):return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while x:=f.read(8*1024*1024):h.update(x)
 return h.hexdigest()
for f in ['FREEZE.json','CPU_FREEZE.json']:
 for n,h in j(R/f).items():assert sha(R/n)==h
s=j(D/'STATUS.json');cpu=j(R/'cpu_attempt1/RESULTS.json');commits=j(D/'COMMITS.json');rets=j(D/'RETURNS.json');checks=j(D/'STAGE_CHECKS.json');lr=j(D/'LAST_READERS.json');res=j(D/'RESIDENCY.json')
order=[16,19,29,49,53,58,70,116];assert s['committed']==s['source_order']==order and len(commits)==len(rets)==8
assert s['new_experts']==7 and s['new_remote_returns']==6 and s['local_returns']==1 and s['new_NoC_packets']==198 and s['reused_expert49']
assert len(checks)==51 and all(v['exact'] and v['different']==0 for v in checks)
assert cpu['slot_order_different']==1157 and len(cpu['source_prefix_sha256'])==8
events={};free={};arenas={}
for rank,stat in s['device'].items():
 es=[json.loads(l) for l in gzip.open(D/('N%02d'%int(rank))/'events.jsonl.gz','rt')];em={e['id']:e for e in es};events[int(rank)]=em
 for e in es:
  assert e['done']>=e['start'] and e['kind'] not in [2,4]
  for dep in e['deps']:assert em[dep]['done']<=e['start']
 ar=[json.loads(l) for l in gzip.open(D/('N%02d'%int(rank))/'sram.jsonl.gz','rt')];arenas[int(rank)]=ar;live={};fr={};peak=0
 for a in ar:
  if a['action']=='alloc':assert a['id'] not in live;live[a['id']]=a['bytes'];peak=max(peak,sum(live.values()))
  else:assert live.pop(a['id'])==a['bytes'];fr[a['id']]=a['cycle']
 assert not live and peak==stat['SRAM_peak_bytes']<=4194304;free[int(rank)]=fr
 for kind,key in [(0,'HB_read_bytes'),(1,'HB_write_bytes')]:assert sum(e['bytes'] for e in es if e['kind']==kind)==stat['counts'][key]
 assert sum(e['requests'] for e in es)==stat['counts']['RAM_transactions'] and stat['HB_address_extent_bytes']<=536870912
assert sum(v['counts'].get('vector_ops',0) for v in s['device'].values())==69284608
for v in lr['SRAM']:
 assert events[v['rank']][v['event']]['done']==v['done_ns'] and all(free[v['rank']][b]>=v['done_ns'] for b in v['buffers'])
for v in lr['regions']:
 rs=[x for x in lr['readers'] if x['rank']==v['rank'] and x['offset']==v['offset']]
 if v['pending']:
  assert v['rank']==0 and v['offset']==s['final_output_offset'] and v['pending']==['downstream_residual'] and v['retired_ns'] is None
 else:
  assert rs and v['retired_ns'] is not None and all(events[x['rank']][x['event']]['done']<=x['done_ns']<=v['retired_ns'] for x in rs)
for r in res:assert r['ready_ns']==events[r['rank']][r['event']]['done'] and r['global_address']==(r['rank']<<29)+r['offset']
for rank in events:
 regions=[v for v in lr['regions'] if v['rank']==rank]
 for i,a in enumerate(regions):
  for b in regions[i+1:]:assert a['offset']+a['bytes']<=b['offset'] or b['offset']+b['bytes']<=a['offset']
des=j(D/'LINK_DESCRIPTORS.json');dm={d['id']:d for d in des};packets=j(D/'LINK_PACKETS.json')
packet_groups={}
for packet in packets:packet_groups.setdefault(packet['descriptor'],[]).append(packet)
for d in des:
 ps=packet_groups.get(d['id'],[]);assert sum(p['bytes'] for p in ps)==d['bytes'] and max(p['arrival_fs'] for p in ps)<=d['commit_fs']
for t in j(D/'TRANSFERS.json'):
 d=dm[t['descriptor']];e=events[t['rank']][t['event']];assert e['kind']==1 and e['bytes']==t['bytes']==d['bytes'] and e['start']*1000000>=d['arrival_fs'] and e['done']*1000000==d['commit_fs']
live={}
for a in j(D/'PINNED_LIFETIMES.json'):
 if a['action']=='acquire':assert len(live)<2;live[a['id']]=a
 else:assert a['id'] in live and a['time_fs']>=a['hold_until'];del live[a['id']]
assert not live
ps=[tuple(map(float,l.split())) for l in (D/'packets.txt').read_text().splitlines()];bs=j(D/'NOC_BATCHES.json');assert len(ps)==198 and len(bs)==6 and {int(v[0]) for v in ps}==set(range(198))
for r in rets:
 if r['kind']=='prior_certified_restore':continue
 assert r['send_ready']<=r['tail']<=r['TX_release'] and r['tail']<=r['HB_ready']<=r['accept_ready']
 assert events[0][r['accept_event']]['start']>=r['HB_ready']
 alloc=next(a for a in arenas[r['owner']] if a['action']=='alloc' and a['label']=='return_TX_e%d'%r['expert']);assert free[r['owner']][alloc['id']]==r['TX_release']
 drain=[e for e in events[r['owner']].values() if e['label']=='return_TX_drain_e%d'%r['expert']];assert len(drain)==1 and drain[0]['done']<=r['send_ready']
 if r['kind']=='native_NoC':
  b=bs[r['native_batch']];q=[p for p in ps if b['first']<=p[0]<b['last']];assert len(q)==33 and b['messages']==[[r['owner'],0,4224]] and b['ends']==[r['tail']] and all(p[3]>=p[2]>=b['earliest']>=r['send_ready'] and p[3]<=r['tail'] for p in q)
 else:assert r['owner']==0 and r['native_batch'] is None
 cap=j(D/'noc_capacity.json');assert cap['peak_input_flits']<=8 and cap['peak_output_flits']<=8 and cap['per_cycle_checks']
for i,c in enumerate(commits):
 assert c['index']==i and c['expert']==order[i] and c['prefix_SHA256']==cpu['source_prefix_sha256'][i]
 e=events[0][c['prefix_event']];assert e['kind']==1 and e['done']==c['commit_done_ns'] and c['return_HB_ready']<=e['start'] and c['weighted_ready']<=e['start']
 if i:assert commits[i-1]['commit_done_ns']<=events[0][c['metadata_reader_event']]['start'] and commits[i-1]['new_acc_offset']==c['prior_acc_offset']
 assert sha(D/('%03d_weighted_BF16.bin'%c['expert']))==c['weighted_SHA256'] and sha(D/('%03d_prefix%d_BF16.bin'%(c['expert'],i)))==c['prefix_SHA256']
assert sha(D/'final_token_BF16.bin')==s['final_sha256']==cpu['final_sha256']
source=False
if '--verify-source' in sys.argv:
 import numpy as np
 import torch
 torch.set_num_threads(1);model=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B');bindings=j(D/'WEIGHT_BINDINGS.json');verified=set();refs={};weighted={};pd=R.parent/'swe_qwen3_activation_noc_20261027_v1/attempt2'
 def bits(t):return t.contiguous().view(torch.uint8).numpy().tobytes()
 def rb(a):
  u=np.ascontiguousarray(a,dtype='<f4').view('<u4');return ((u+np.uint32(0x7fff)+((u>>16)&1))>>16).astype('<u2')
 for b in bindings:
  e=b['expert'];r=next(v for v in cpu['rows'] if v['expert']==e);frame=(pd/('receiver_%03d.bin'%r['slot'])).read_bytes();x=torch.from_numpy(np.frombuffer(frame[128:],dtype='<u2').copy()).view(torch.bfloat16).reshape(1,2048);weights={}
  for name,v in b['weights'].items():
   path=model/v['shard']
   if path not in verified:assert sha(path)==v['shard_sha256'];verified.add(path)
   with path.open('rb') as f:f.seek(v['file_offset']);data=f.read(v['bytes'])
   assert hashlib.sha256(data).hexdigest()==v['sha256'];weights[name]=torch.from_numpy(np.frombuffer(data,dtype='<u2').copy()).view(torch.bfloat16).reshape(v['shape'])
  gate=torch.nn.functional.linear(x,weights['gate_proj']);up=torch.nn.functional.linear(x,weights['up_proj']);silu=torch.nn.functional.silu(gate);product=silu*up;down=torch.nn.functional.linear(product,weights['down_proj']);refs[e]=down
  if e!=49:
   for name,value in [('gate',gate),('up',up),('silu',silu),('product',product),('down',down)]:assert bits(value)==(D/('%03d_%s_BF16.bin'%(e,name))).read_bytes()
   # Independent NumPy64lane projection tree, compared against actual FP32 residency hashes.
   for name,input_value in [('gate',x),('up',x),('down',product)]:
    a=input_value.float().numpy().reshape(-1);w=weights[name+'_proj'].float().numpy();lanes=np.zeros((64,w.shape[0]),dtype='<f4')
    for k in range(len(a)):lanes[k%64]=np.add(lanes[k%64],a[k]*w[:,k],dtype=np.float32)
    for off in [32,16,8,4,2,1]:lanes[:off]=np.add(lanes[:off],lanes[off:2*off],dtype=np.float32)
    label='e%d_%s_out_FP32'%(e,name);entry=next(v for v in res if v['rank']==r['owner'] and v['label']==label);assert hashlib.sha256(lanes[0].tobytes()).hexdigest()==entry['sha256']
  returned=(R.parent/'swe_qwen3_expert_tail_20261028_v1/native_attempt1/returned_frame.bin').read_bytes() if e==49 else (D/('return_%03d.bin'%e)).read_bytes()
  assert returned[:32]==frame[:32] and returned[128:]==bits(down) and returned[64:96]==hashlib.sha256(returned[128:]).digest()
  assert struct.unpack('<8sIIQQ',returned[32:64])==(b'SWERET1\0',r['owner'],0,r['slot'],4096)
  weight=torch.from_numpy(np.array([r['weight_bits']],dtype='<u2')).view(torch.bfloat16)[0];weighted[e]=down*weight
  assert bits(weighted[e])==(D/('%03d_weighted_BF16.bin'%e)).read_bytes()
  independent=rb(down.float().numpy()*weight.float().numpy());assert independent.tobytes()==bits(weighted[e])
 prefix=torch.zeros((1,2048),dtype=torch.bfloat16);ind=np.zeros((1,2048),dtype='<u2')
 for i,e in enumerate(order):
  prefix.index_add_(0,torch.tensor([0]),weighted[e]);assert bits(prefix)==(D/('%03d_prefix%d_BF16.bin'%(e,i))).read_bytes()
  fa=(ind.astype('<u4')<<16).view('<f4');ind=rb(fa+weighted[e].float().numpy());assert ind.tobytes()==bits(prefix)
 assert bits(prefix)==(D/'final_token_BF16.bin').read_bytes();old=j(pd/'SOURCE_BINDING.json')
 for name in ['olmoearth_v3_6_integration_20261025_v1/run_integrated.py','olmoearth_v3_6_integration_20261025_v1/canonical_ram.yaml','olmoearth_v3_6_multi_npu_20261025_v1/noc_bridge_v2']+['olmoearth_v3_6_multi_npu_20261025_v1/libolmo_native_%02d.so'%rank for rank in events]:
  p=R.parent/name;assert sha(p)==old[str(p)]['sha256']
 source=True
out=dict(state='PASS_LIMITED_FIXED_TOKEN_TOP8_AUDIT',source_weights_CPU_stages_and_independent_trees_verified=source,experts=8,new_experts=7,source_order=order,stage_checks=len(checks),BF16_different=0,events=sum(len(es) for es in events.values()),vector_ops=69284608,RAM_transactions=sum(v['counts']['RAM_transactions'] for v in s['device'].values()),SRAM_peak_bytes=max(v['SRAM_peak_bytes'] for v in s['device'].values()),negative_controls=len(s['negative_controls']),new_NoC_packets=198,slot_order_negative_different=1157,final_sha256=s['final_sha256'],final_output_pending=s['final_output_pending'],batch='DIFFERENCES_RETAINED',softmax_FP32='FAILED_RETAINED',physical_NPU_runs=0)
target=Path(next((x for x in sys.argv[1:] if not x.startswith('--')),str(D/'INDEPENDENT_AUDIT.json')));target.write_text(json.dumps(out,indent=2));print(json.dumps(out))

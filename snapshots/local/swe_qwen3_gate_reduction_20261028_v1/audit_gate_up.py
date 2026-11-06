import gzip,hashlib,json,sys
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/'native_attempt1'
def j(p):return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(8*1024*1024):h.update(b)
 return h.hexdigest()
for freeze in ['CPU_FREEZE.json','TREE_FREEZE.json','TREE_FREEZE_v2.json','UP_FREEZE.json','NATIVE_FREEZE.json']:
 for n,h in j(R/freeze).items():assert sha(R/n)==h
s=j(D/'STATUS.json');stages={v['projection']:v for v in s['stages']};assert set(stages)=={'gate_proj','up_proj'}
assert stages['gate_proj']['done_ns']==s['gate_verified_ns']<stages['up_proj']['start_ns']
assert all(v['BF16_exact'] and v['different']==0 for v in s['checks'].values())
for sub in ['tree_cpu_attempt2','up_cpu_attempt1']:
 c=j(R/sub/'RESULTS.json');assert c['outputs']==138240 and c['single_token_source_different']==0 and c['batch_source_different']==21
dispatch=j(R/'DISPATCH_INSPECTION.json');assert any('AVX512' in v['symbol'] and v['pointer_is_null'] for v in dispatch['BF16_GEMV_registrations'])
assert any('AVX2' in v['symbol'] and not v['pointer_is_null'] for v in dispatch['BF16_GEMV_registrations'])
ev=[json.loads(l) for l in gzip.open(D/'N01/events.jsonl.gz','rt')];em={e['id']:e for e in ev}
for e in ev:
 assert e['done']>=e['start'] and e['kind'] not in [2,4]
 for dep in e['deps']:assert em[dep]['done']<=e['start']
arena=[json.loads(l) for l in gzip.open(D/'N01/sram.jsonl.gz','rt')];live={};free={};peak=0
for a in arena:
 if a['action']=='alloc':assert a['id'] not in live;live[a['id']]=a['bytes'];peak=max(peak,sum(live.values()))
 else:assert live.pop(a['id'])==a['bytes'];free[a['id']]=a['cycle']
assert not live and peak==s['device']['SRAM_peak_bytes']<=4194304
for v in j(D/'ARITHMETIC_LAST_READERS.json'):
 assert em[v['last_arithmetic_event']]['done']==v['done_ns'] and v['remaining']==0
 assert free[v['input_buffer']]>=v['done_ns'] and free[v['weight_buffer']]>=v['done_ns']
hb=j(D/'HB_LAST_READERS.json');assert hb['inbox_pending']==[] and hb['inbox_retained'] and hb['outputs_retained']
for name,rs in hb['projections'].items():
 assert len(rs)==12 and {v['tile'] for v in rs}==set(range(12))
 assert max(v['done_ns'] for v in rs)==stages[name]['done_ns']<=hb['input_last_reader_ns']
res=j(D/'RESIDENCY.json');regions={r['label']:r for r in res}
for i,a in enumerate(res):
 assert a['global_address']==(1<<29)+a['local'] and a['ready_ns']==em[a['commit_event']]['done']
 for b in res[i+1:]:assert a['local']+a['bytes']<=b['local'] or b['local']+b['bytes']<=a['local']
for proj,label in [('gate_proj','expanded_gate'),('up_proj','expanded_up')]:
 assert regions[label]['ready_ns']<=stages[proj]['start_ns'] and regions['expanded_input']['ready_ns']<=stages[proj]['start_ns']
des=j(D/'LINK_DESCRIPTORS.json');dm={d['id']:d for d in des};pack=j(D/'LINK_PACKETS.json')
for d in des:
 ps=[p for p in pack if p['descriptor']==d['id']];assert sum(p['bytes'] for p in ps)==d['bytes'] and max(p['arrival_fs'] for p in ps)<=d['commit_fs']
for t in j(D/'TRANSFERS.json'):
 d=dm[t['descriptor']];e=em[t['event']];assert e['kind']==1 and e['bytes']==t['bytes']==d['bytes']
 assert e['start']*1000000>=d['arrival_fs'] and e['done']*1000000==d['commit_fs']
 if t['label']=='expanded_up':assert e['start']>s['gate_verified_ns']
live={}
for a in j(D/'PINNED_LIFETIMES.json'):
 if a['action']=='acquire':assert len(live)<2;live[a['id']]=a
 else:assert a['id'] in live and a['time_fs']>=a['hold_until'];del live[a['id']]
assert not live
counts=s['device']['counts'];assert counts['vector_ops']==6486528
for k,key in [(0,'HB_read_bytes'),(1,'HB_write_bytes')]:assert sum(e['bytes'] for e in ev if e['kind']==k)==counts[key]
assert sum(e['requests'] for e in ev)==counts['RAM_transactions']
source=False
if '--verify-source' in sys.argv:
 import numpy as np
 parent=R.parent/'swe_qwen3_activation_noc_20261027_v1/attempt2';wire=(parent/'receiver_000.bin').read_bytes();x=(np.frombuffer(wire[128:],dtype='<u2').astype('<u4')<<16).view('<f4')
 model=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B');weights=j(D/'WEIGHT_BINDING.json')['selected'];verified=set()
 for proj in ['gate_proj','up_proj','down_proj']:
  b=weights[proj];p=model/b['shard']
  if p not in verified:assert sha(p)==b['verified_shard_sha256'];verified.add(p)
  with p.open('rb') as f:f.seek(b['file_offset']);blob=f.read(b['bytes'])
  assert hashlib.sha256(blob).hexdigest()==b['sha256'] and b['dtype']=='BF16'
  if proj=='down_proj':continue
  w=(np.frombuffer(blob,dtype='<u2').astype('<u4')<<16).view('<f4').reshape(b['shape']);lanes=np.zeros((64,768),dtype='<f4')
  for k in range(2048):lanes[k%64]=np.add(lanes[k%64],x[k]*w[:,k],dtype=np.float32)
  for offset in [32,16,8,4,2,1]:lanes[:offset]=np.add(lanes[:offset],lanes[offset:2*offset],dtype=np.float32)
  y=lanes[0];assert y.tobytes()==(D/(proj+'_FP32.bin')).read_bytes()
  u=y.view('<u4');bf=((u+np.uint32(0x7fff)+((u>>16)&1))>>16).astype('<u2').tobytes()
  assert bf==(D/(proj+'_BF16.bin')).read_bytes()==(D/(proj+'_CPU_BF16.bin')).read_bytes()
 assert sha(Path(dispatch['library']))==dispatch['library_sha256'];source=True
 old=j(parent/'SOURCE_BINDING.json')
 for name in ['olmoearth_v3_6_integration_20261025_v1/run_integrated.py','olmoearth_v3_6_integration_20261025_v1/canonical_ram.yaml','olmoearth_v3_6_multi_npu_20261025_v1/libolmo_native_01.so']:
  path=R.parent/name;assert sha(path)==old[str(path)]['sha256']
out=dict(state='PASS_LIMITED_M1_GATE_UP_CAUSALITY',original_weights_and_independent_arithmetic_verified=source,events=len(ev),vector_ops=counts['vector_ops'],RAM_transactions=counts['RAM_transactions'],SRAM_peak_bytes=peak,negative_controls=len(s['negative_controls']),gate_BF16_different=0,up_BF16_different=0,batch_source_differences_retained=21,softmax_FP32='FAILED_RETAINED',physical_NPU_runs=0)
target=Path(next((a for a in sys.argv[1:] if not a.startswith('--')),str(D/'INDEPENDENT_AUDIT.json')));target.write_text(json.dumps(out,indent=2));print(json.dumps(out))

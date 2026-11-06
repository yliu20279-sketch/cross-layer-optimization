import gzip,hashlib,json,sys
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/'attempt1'
def j(p):return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while c:=f.read(8*1024*1024):h.update(c)
 return h.hexdigest()
s=j(D/'STATUS.json');binding=j(D/'WEIGHT_BINDING.json');res=j(D/'RESIDENCY.json');tr=j(D/'TRANSFERS.json')
for n,h in j(R/'FREEZE.json').items():assert sha(R/n)==h
e=[json.loads(l) for l in gzip.open(D/'N01/events.jsonl.gz','rt')];em={v['id']:v for v in e}
for v in e:
 assert v['done']>=v['start'] and v['kind'] not in [2,4]
 for dep in v['deps']:assert em[dep]['done']<=v['start']
ar=[json.loads(l) for l in gzip.open(D/'N01/sram.jsonl.gz','rt')];live={};peak=0;free={}
for a in ar:
 if a['action']=='alloc':assert a['id'] not in live;live[a['id']]=a['bytes'];peak=max(peak,sum(live.values()))
 elif a['action']=='free':assert live.pop(a['id'])==a['bytes'];free[a['id']]=a['cycle']
assert not live and peak==s['device']['SRAM_peak_bytes'] and peak<=4194304
for v in j(D/'ARITHMETIC_LAST_READERS.json'):
 assert v['remaining']==0 and em[v['last_arithmetic_event']]['done']==v['done_ns']
 assert free[v['weight_buffer']]>=v['done_ns'] and free[v['input_buffer']]>=v['done_ns']
hb=j(D/'HB_LAST_READERS.json');assert len(hb['expanded_tile_readers'])==12 and hb['inbox_pending']==['up_proj']
assert {v['tile'] for v in hb['expanded_tile_readers']}==set(range(12))
assert max(v['done_ns'] for v in hb['expanded_tile_readers'])<=hb['expanded_retire_ns']
for r in res:
 assert r['ready_ns']==em[r['commit_event']]['done']<=s['compute_start_ns']
 assert r['global_address']==(1<<29)+r['local']
for i,a in enumerate(res):
 for b in res[i+1:]:assert a['local']+a['bytes']<=b['local'] or b['local']+b['bytes']<=a['local']
ds=j(D/'LINK_DESCRIPTORS.json');dm={v['id']:v for v in ds};packets=j(D/'LINK_PACKETS.json')
for d in ds:
 ps=[p for p in packets if p['descriptor']==d['id']];assert sum(p['bytes'] for p in ps)==d['bytes']
 assert d['ready_fs']<=d['issue_fs']<=d['iommu_done_fs'] and max(p['arrival_fs'] for p in ps)<=d['commit_fs']
for t in tr:
 ev=em[t['event']];d=dm[t['descriptor']]
 assert ev['kind']==1 and ev['bytes']==t['bytes']==d['bytes'] and ev['done']*1000000==d['commit_fs']
 assert ev['start']*1000000>=d['arrival_fs']
leases=j(D/'PINNED_LIFETIMES.json');active={}
for a in leases:
 if a['action']=='acquire':assert len(active)<2;active[a['id']]=a
 else:assert a['id'] in active and a['time_fs']>=a['hold_until'];del active[a['id']]
assert not active
assert binding['full_model_host_address_extent']+binding['runtime_IO_reserved']<=128*2**30
assert s['parent_plus_new_conservative_HB_bytes']<8*2**30
counts=s['device']['counts']
assert counts['vector_ops']==2*768*2048+768
for kind,key in [(0,'HB_read_bytes'),(1,'HB_write_bytes')]:assert sum(v['bytes'] for v in e if v['kind']==kind)==counts[key]
assert sum(v['requests'] for v in e)==counts['RAM_transactions']
assert len(s['negative_controls'])==len(set(s['negative_controls']))==9
source=False
if '--verify-source' in sys.argv:
 import numpy as np
 model=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B');verified=set();weights={}
 for proj,b in binding['selected'].items():
  p=model/b['shard']
  if p not in verified:assert sha(p)==b['verified_shard_sha256'];verified.add(p)
  with p.open('rb') as f:f.seek(b['file_offset']);blob=f.read(b['bytes'])
  assert hashlib.sha256(blob).hexdigest()==b['sha256'] and b['dtype']=='BF16'
  weights[proj]=(np.frombuffer(blob,dtype='<u2').astype('<u4')<<16).view('<f4').reshape(b['shape'])
 parent=R.parent/'swe_qwen3_activation_noc_20261027_v1/attempt2';wire=(parent/'receiver_000.bin').read_bytes()
 x=(np.frombuffer(wire[128:],dtype='<u2').astype('<u4')<<16).view('<f4');w=weights['gate_proj']
 y=np.zeros(768,dtype='<f4')
 for k in range(2048):y=np.add(y,np.multiply(x[k],w[:,k],dtype=np.float32),dtype=np.float32)
 assert y.tobytes()==(D/'gate_FP32.bin').read_bytes()
 u=y.view('<u4');bf=((u+np.uint32(0x7fff)+((u>>16)&1))>>16).astype('<u2')
 assert bf.tobytes()==(D/'gate_BF16.bin').read_bytes()
 old=j(parent/'SOURCE_BINDING.json')
 for p in ['olmoearth_v3_6_integration_20261025_v1/run_integrated.py','olmoearth_v3_6_integration_20261025_v1/canonical_ram.yaml','olmoearth_v3_6_multi_npu_20261025_v1/libolmo_native_01.so']:
  path=R.parent/p;assert sha(path)==old[str(path)]['sha256']
 source=True
out=dict(state='PASS_LIMITED_INDEPENDENT_EXPERT_GATE_AUDIT',source_weights_and_numpy_arithmetic_verified=source,checks=s['checks'],events=len(e),SRAM_peak_bytes=peak,negative_controls=len(s['negative_controls']),RAM_transactions=counts['RAM_transactions'],H2D_bytes=sum(d['bytes'] for d in ds if d['direction']=='H2D'),D2H_bytes=sum(d['bytes'] for d in ds if d['direction']=='D2H'),softmax_FP32='FAILED_RETAINED',physical_NPU_runs=0)
target=Path(next((x for x in sys.argv[1:] if not x.startswith('--')),str(D/'INDEPENDENT_AUDIT.json')));target.write_text(json.dumps(out,indent=2));print(json.dumps(out))

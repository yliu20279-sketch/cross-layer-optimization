import json,gzip,hashlib,ctypes as C
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent;D=R/'continuous_attempt1';OLD=R.parent/'swe_qwen3_step3_four_gates_20261028_v1'
def j(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert all(sha(R/n)==h for n,h in j(R/'CONTINUOUS_FREEZE.json').items())
cs=j(D/'CHECKS.json');assert len([v for v in cs if v['strict']])==12 and all(v['exact'] for v in cs if v['strict'])
files=j(D/'FILES.json');assert len(files)==56
for v in files:
 assert sha(D/v['path'])==v['sha256'] and (D/v['path']).read_bytes()==(OLD/'reference_attempt1'/v['path']).read_bytes()
events=[json.loads(x) for x in gzip.open(D/'N00/events.jsonl.gz','rt')];ev={x['id']:x for x in events}
for e in events:
 assert e['done']>=e['start']
 for dep in e['deps']:assert dep in ev and dep<e['id'] and ev[dep]['done']<=e['start']
s=j(D/'COUPLED_STATUS.json');assert len(ev)==s['device']['counts']['events'];assert sum(e['requests'] for e in events)==s['device']['counts']['RAM_transactions']
ns=j(D/'NODES.json');vn=j(D/'NATIVE_VECTOR_NODES.json');on=j(OLD/'coupled_attempt3/NODES.json');res={v['offset']:v for v in j(OLD/'coupled_attempt3/RESIDENCY.json')};old=[v for v in on if v['label'] in ['host:add_bf16','host:mul_bf16']];assert len(old)==len(vn)
for v,o in zip(vn,old):
 assert v['phase']==o['phase'] and v['layer']==o['layer'] and v['op']==('mul' if o['label']=='host:mul_bf16' else 'add')
 assert v['sha256']==res[o['offset']]['sha256']
 assert ev[v['compute_event']]['done']<=ev[v['commit_event']]['start']
 for parent in v['parents']:assert ns[parent]['ready_ns']<=ev[v['compute_event']]['start']
for n in ns:
 assert n['readers']
 for reader in n['readers']:assert reader['done_ns']>=n['ready_ns']
lr=j(D/'LAST_READERS.json')
for region in lr['regions']:
 assert region['offset']+region['bytes']<=512*2**20
 assert (region['retired_ns'] is None)==bool(region['pending'])
assert s['device']['SRAM_peak_bytes']<=4*2**20
handoffs=j(D/'LAYER_HANDOFFS.json');assert len(handoffs)==2 and all(not h['restored'] and h['source_done_ns']<=h['consumer_start_ns'] for h in handoffs)
kv=j(D/'KV_EVENTS.json');assert [(v['past'],v['length']) for v in kv]==[(0,19),(0,19),(19,20),(19,20)]
assert not any(v['name'] in ['BF16_add','BF16_multiply'] for v in j(D/'HOST_FALLBACK_OPS.json'))
# Independent NumPy finite-domain challenge for C RNE; no PyTorch arithmetic.
lib=C.CDLL(str(R/'libvector.so'));lib.binary.argtypes=[C.c_void_p]*3+[C.c_int]*2
rng=np.random.default_rng(20261029);a=rng.uniform(-8,8,65536).astype('<f4');b=rng.uniform(-8,8,65536).astype('<f4')
def bf(x):
 u=x.view('<u4');return ((u+0x7fff+((u>>16)&1))>>16).astype('<u2')
aa=bf(a);bb=bf(b);af=(aa.astype('<u4')<<16).view('<f4');bfv=(bb.astype('<u4')<<16).view('<f4')
for mul in [0,1]:
 y=np.empty_like(aa);lib.binary(aa.ctypes.data,bb.ctypes.data,y.ctypes.data,len(y),mul);expected=bf(af*bfv if mul else af+bfv);assert np.array_equal(y,expected)
norm=j(D/'NORM_NODES.json');nc=j(D/'NORM_CHECKS.json');assert len(norm)==16 and len(nc)==64 and all(c['exact'] and c['different']==0 for c in nc)
for v in norm:
 assert v['K'] in [128,2048] and ev[v['compute_event']]['done']<=ev[v['commit_event']]['start']
 assert ns[v['input_node']]['ready_ns']<=ev[v['compute_event']]['start']
assert not any(v['name']=='rmsnorm' for v in j(D/'HOST_FALLBACK_OPS.json'))
controls=j(R/'CONTROL_RESULTS.json');assert len(controls)==72 and all(c['different']==0 for c in controls)
out=dict(state='PASS_LIMITED_CONTINUOUS_NORM_AUDIT',norm_calls=16,norm_stage_checks=64,control_checks=72,control_elements=sum(c['elements'] for c in controls),strict_layer_KV_checks=12,stage_files=56,vector_node_hashes_vs_previous=len(vn),independent_C_elements=131072,events=len(events),RAM_transactions=s['device']['counts']['RAM_transactions'],SRAM_peak_bytes=s['device']['SRAM_peak_bytes'],host_fallback_ops=s['host_fallback_ops'],handoffs=2,KV_appends=4,GPU_differences='retained',full_timing='NOT_CERTIFIED')
(R/'INDEPENDENT_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))

import copy,csv,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
R=HERE/'unified_layers';D=R/'case1'
REF=HERE.parent.parent/'swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1'
def j(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def nodes_ok(nodes):
 for i,n in enumerate(nodes):
  assert n['id']==i and 32*2**20<=n['offset']<n['offset']+n['bytes']<=512*2**20
  assert n['ready']>=n['commit']
  for rd in n['readers']:assert rd['done']>=n['ready']
  for p in n['parents']:assert p<i and nodes[p]['ready']<=n['commit']
  if i:assert nodes[i-1]['offset']+nodes[i-1]['bytes']<=n['offset']
def weights_ok(mat,tx):
 groups=[]
 for t in tx:
  if int(t['address'])>=32*2**20:continue
  if t['operation']=='STORE' and int(t['address'])==0:groups.append([])
  assert groups;groups[-1].append(t)
 assert len(groups)==len(mat)==759
 for m,g in zip(mat,groups):
  assert m['weight_bytes']<=32*2**20 and m['SRAM_working_set_bound']<=4*2**20
  for op in ['STORE','LOAD']:assert sum(int(t['bytes']) for t in g if t['operation']==op)==m['weight_bytes']
 for previous,following in zip(groups,groups[1:]):
  last_reader=max(int(t['issue_cycle'])+int(t['phase1_elapsed_cycles']) for t in previous if t['operation']=='LOAD')
  assert last_reader<=int(following[0]['issue_cycle'])
files=j(D/'FILES.json');assert len(files)==56
for v in files:
 assert sha(D/v['path'])==v['sha256'] and (D/v['path']).read_bytes()==(REF/v['path']).read_bytes()
checks=j(D/'CHECKS.json');strict=[v for v in checks if v['strict']]
assert len(strict)==12 and all(v['exact'] and v['different']==0 for v in strict)
nodes=j(D/'NODES.json');nodes_ok(nodes)
mat=j(D/'MATRIX_CALLS.json');tx=list(csv.DictReader((D/'npusim_dram_transactions_1_0.csv').open()));weights_ok(mat,tx)
kv=j(D/'KV_EVENTS.json');assert [(v['past'],v['length']) for v in kv]==[(0,19),(0,19),(19,20),(19,20)]
negative=[]
def reject(name,fn):
 try:fn()
 except AssertionError:negative.append(name);return
 raise RuntimeError('negative control not rejected: '+name)
n=copy.deepcopy(nodes);n[1]['offset']=n[0]['offset'];reject('overlapping_HB_allocations',lambda:nodes_ok(n))
n=copy.deepcopy(nodes);n[0]['readers'][0]['done']=n[0]['ready']-1;reject('reader_before_ready',lambda:nodes_ok(n))
n=copy.deepcopy(nodes);n[1]['parents']=[1];reject('noncausal_parent',lambda:nodes_ok(n))
n=copy.deepcopy(nodes);n[-1]['offset']=512*2**20;reject('HB_capacity_overrun',lambda:nodes_ok(n))
t=copy.deepcopy(tx);v=next(v for v in t if int(v['address'])<32*2**20);v['bytes']=str(int(v['bytes'])+32);reject('weight_payload_length_corruption',lambda:weights_ok(mat,t))
m=copy.deepcopy(mat);m[0]['SRAM_working_set_bound']=4*2**20+1;reject('static_SRAM_bound_overrun',lambda:weights_ok(m,tx))
t=copy.deepcopy(tx);starts=[v for v in t if v['operation']=='STORE' and int(v['address'])==0];starts[1]['issue_cycle']='0';reject('weight_overwrite_before_last_reader',lambda:weights_ok(mat,t))
cpu_missing=[phase for phase in ['prefill','decode'] if not (R/'cpu_data'/(phase+'_ACTUAL.bin')).exists()]
out=dict(state='PASS_LIMITED_STAGE_AND_RECORDED_DEPENDENCY_AUDIT_CPU_ACCEPTANCE_FAILED',strict_checks=12,stage_files=56,nodes=len(nodes),weight_versions=len(mat),negative_controls=negative,CPU_missing_results=cpu_missing,CPU_PASS=(R/'cpu_data/CPU_PASS.json').exists(),full_steps_1_7=False,scope='First run numeric stage audit only. Decode FIFO EOF prevents CPU end-to-end acceptance. Immutable retained buffers avoid reuse; this does not certify an eviction allocator or native SRAM residency.')
assert cpu_missing==['decode'] and not out['CPU_PASS']
(HERE/'LOCAL_STAGE_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))

import json,hashlib,collections
from pathlib import Path
def check(root,round):
 R=Path(root);D=R/('case%d'%round);B=R.parent;ref=B/'swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1'
 def j(p):return json.loads(p.read_text())
 def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
 expected=j(R/'EXPECTED.json');params=j(R/'PARAMETERS.json');files=j(D/'FILES.json');checks=[v for v in j(D/'CHECKS.json') if v['strict']]
 assert len(files)==56 and len(checks)==12 and all(v['exact'] and v['different']==0 for v in checks)
 for v in files:assert sha(D/v['path'])==v['sha256'] and (D/v['path']).read_bytes()==(ref/v['path']).read_bytes()
 cpu=j(D/'CPU_PASS.json');gw=j(D/'GATEWAY_PASS.json');assert cpu['state']=='PASS_FULL_TWO_LAYER_PREFILL_DECODE' and gw['state']=='PASS_FULL_LAYER_SERVICE'
 assert cpu['model_mapped_bytes']==j(R/'HOST_BACKING.json')['model_file_bytes']
 for phase in ['prefill','decode']:
  v=next(v for v in files if v['phase']==phase and v['layer']==1 and v['stage']=='output');assert (D/(phase+'_CPU_ACTUAL.bin')).read_bytes()==(D/v['path']).read_bytes()
 mat=j(D/'MATRIX_CALLS.json');rpc=j(D/'RPC.json');assert len(mat)==759 and sum(v['param'] is not None for v in mat)==503
 fetch=[v for v in rpc if v['kind']=='FETCH'];remote=[v for v in rpc if v['kind']=='REMOTE']
 assert len(fetch)==expected['parameter_fetches'] and len(remote)==expected['remote_matrices']
 assert cpu['remote_jobs']==gw['remote_jobs']==len(remote) and cpu['parameter_fetches']==gw['parameter_fetches']==len(fetch)
 assert [v['sequence'] for v in rpc]==list(range(1,len(rpc)+1))
 for v in rpc:assert v['weight_sha256']==params[v['param']]['sha256'] and v['complete']>=v['start']
 peers={}
 for rank in range(1,16):
  jobs=j(D/('N%02d'%rank)/'JOBS.json');assert len(jobs)==expected['expert_matrix_calls_by_owner'][str(rank)]
  for a,b in zip(jobs,jobs[1:]):assert a['returned']<=b['start']
  for v in jobs:
   assert v['owner']==rank and v['weight_last_reader']<=v['compute_done']<=v['returned'];assert v['sequence'] not in peers;peers[v['sequence']]=v
 assert len(peers)==len(remote)
 for v in remote:
  p=peers[v['sequence']]
  for key in ['param','owner','M','N','K','input_sha256','weight_sha256','output_sha256']:assert p[key]==v[key]
 nodes=j(D/'NODES.json')
 for i,n in enumerate(nodes):
  assert n['offset']>=32*2**20 and n['offset']+n['bytes']<=512*2**20 and n['ready']>=n['commit']
  assert n['retired_at']>=n['last_consumer_barrier_start']>=max([n['ready']]+[v['done'] for v in n['readers']])
  for rd in n['readers']:assert rd['done']>=n['ready']
  for parent in n['parents']:assert parent<i and nodes[parent]['ready']<=n['commit']
 kv=j(D/'KV_EVENTS.json');assert [(v['past'],v['length']) for v in kv]==[(0,19),(0,19),(19,20),(19,20)]
 assert all(v['SRAM_working_set_bound']<=4*2**20 for v in mat)
 return dict(state='PASS_LIMITED_FULL_16_NPU_FUNCTIONAL_CASE',round=round,stage_files=56,strict_output_KV_checks=12,CPU_outputs=2,matrix_calls=len(mat),remote_matrices=len(remote),host_parameter_fetches=len(fetch),NPU_count=16,full_target_timing=False,full_steps_1_7=False)

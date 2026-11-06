import csv,json,hashlib,math,re
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/'case1';B=R.parent.parent;REF=B/'swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1'
def j(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert all(sha(R/n)==h for n,h in j(R/'WORKER_FREEZE.json').items())
checks=j(D/'CHECKS.json');assert len([v for v in checks if v['strict']])==12 and all(v['exact'] and v['different']==0 for v in checks if v['strict'])
files=j(D/'FILES.json');assert len(files)==56
for v in files:assert sha(D/v['path'])==v['sha256'] and (D/v['path']).read_bytes()==(REF/v['path']).read_bytes()
for phase in ['prefill','decode']:
 v=next(v for v in files if v['phase']==phase and v['layer']==1 and v['stage']=='output');assert (R/'cpu_data'/(phase+'_ACTUAL.bin')).read_bytes()==(D/v['path']).read_bytes()
summary=j(D/'UNIFIED_SUMMARY.json');nodes=j(D/'NODES.json');ops=j(D/'OPS.json');mat=j(D/'MATRIX_CALLS.json');kv=j(D/'KV_EVENTS.json')
assert len(mat)==759 and [(v['past'],v['length']) for v in kv]==[(0,19),(0,19),(19,20),(19,20)]
assert all(n['offset']+n['bytes']<=512*2**20 and n['offset']>=32*2**20 for n in nodes)
for a,b in zip(nodes,nodes[1:]):assert a['offset']+a['bytes']<=b['offset']
for n in nodes:
 assert n['ready']>=n['commit']
 for rd in n['readers']:assert rd['done']>=n['ready']
 for parent in n['parents']:assert parent<n['id'] and nodes[parent]['ready']<=n['commit']
for a,b in zip(ops,ops[1:]):assert a['start']<=a['complete']<=b['start']
assert all(m['SRAM_working_set_bound']<=4*2**20 and m['weight_bytes']<=32*2**20 for m in mat)
prog=list(csv.DictReader((D/'program.csv').open()));assert len(prog)==len(ops)
for a,b in zip(prog,ops):assert a['label']==b['label'] and int(a['ops'])==b['ops'] and int(a['complete'])==b['complete']
tx=list(csv.DictReader((D/'npusim_dram_transactions_1_0.csv').open()));groups=[]
for t in tx:
 if int(t['address'])>=32*2**20:continue
 if t['operation']=='STORE' and int(t['address'])==0:groups.append([])
 assert groups;groups[-1].append(t)
assert len(groups)==len(mat)
for m,g in zip(mat,groups):
 assert sum(int(t['bytes']) for t in g if t['operation']=='STORE')==m['weight_bytes']
 assert sum(int(t['bytes']) for t in g if t['operation']=='LOAD')==m['weight_bytes']
for t in tx:assert int(t['phase1_elapsed_cycles'])>=0
fallback=j(D/'ALL_FUNCTIONAL_OPS.json');assert sum(v['op']=='explicit_F_silu' for v in fallback)==161
log=(R/'RUN1.log').read_text();statuses=[int(v) for v in re.findall(r'terminate with status = (\d+)',log)];assert len(statuses)==4 and all(v==0 for v in statuses)
delays=(R/'run1/delayInfo.txt').read_text().splitlines();assert delays
out=dict(state='PASS_LIMITED_UNIFIED_TWO_LAYER_FUNCTIONAL_AUDIT',strict_layer_KV_checks=12,stage_files_exact=56,CPU_result_checks=2,matrix_calls=759,weight_versions=759,weight_byte_flows_exact=True,KV_appends=4,immutable_activation_nodes=len(nodes),HB_extent=summary['HB_extent'],software_event_ops=len(ops),Silu_calls_explicit=161,client_transactions=len(tx),NoC_delay_records=len(delays),all_subprocesses_zero=True,precision='original BF16',host_GiB=128,architectural_HB_GiB=8,active_HB_MiB=512,scope='one active NPU/HB diagnostic topology; all values/weights through real external HB; host weight ingress/CPU fallback costs provisional, not full16 or complete system timing; external CPU input node layer tag on decode inherits1 but immediately consumed as layer0 per frozen worker',full_steps_1_7=False)
(R/'FULL_FUNCTIONAL_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))

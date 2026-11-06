import tarfile,json,hashlib,csv,collections,math
from pathlib import Path
H=Path(__file__).resolve().parent;pack=H/(H.name+'_PHASE1_REVIEW.tar.gz');review=H/'review';review.mkdir(exist_ok=True)
assert hashlib.sha256(pack.read_bytes()).hexdigest()=='d4d21bd28c44e0851643b3bfa017b31510a0dcbdd01895b05337490938a88680'
with tarfile.open(pack) as t:
 assert all(not n.startswith('/') and '..' not in Path(n).parts for n in t.getnames());t.extractall(review,filter='data')
R=review/H.name;D=R/'case1';ref=H.parent/'swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1'
def j(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=j(R/'PHASE1_MANIFEST.json');assert len(manifest)==160
for v in manifest:assert (R/v['path']).stat().st_size==v['bytes'] and sha(R/v['path'])==v['sha256']
for n,h in j(R/'FREEZE.json').items():assert sha(R/n)==h
files=j(D/'FILES.json');assert len(files)==56
for v in files:assert sha(D/v['path'])==v['sha256'] and (D/v['path']).read_bytes()==(ref/v['path']).read_bytes()
checks=[v for v in j(D/'CHECKS.json') if v['strict']];assert len(checks)==12 and all(v['exact'] and v['different']==0 for v in checks)
for phase in ['prefill','decode']:
 v=next(v for v in files if v['phase']==phase and v['layer']==1 and v['stage']=='output');assert (D/(phase+'_CPU_ACTUAL.bin')).read_bytes()==(D/v['path']).read_bytes()
mat=j(D/'MATRIX_CALLS.json');rpc=j(D/'RPC.json');assert len(mat)==759 and sum(v['param'] is not None for v in mat)==503
remote={v['sequence']:v for v in rpc if v['kind']=='REMOTE'};assert len(remote)==450 and sum(v['kind']=='FETCH' for v in rpc)==61
params=j(R/'PARAMETERS.json');seen=set()
for rank in range(1,16):
 jobs=j(D/('N%02d'%rank)/'JOBS.json')
 for a,b in zip(jobs,jobs[1:]):assert a['returned']<=b['start']
 for v in jobs:
  source=remote[v['sequence']];assert v['sequence'] not in seen;seen.add(v['sequence'])
  for k in ['param','owner','M','N','K','weight_sha256','input_sha256','output_sha256']:assert v[k]==source[k]
  assert v['owner']==rank and v['weight_sha256']==params[v['param']]['sha256'] and v['weight_last_reader']<=v['compute_done']<=v['returned']
assert seen==set(remote)
clocks=list(csv.DictReader((R/'run1/clock_round1.csv').open()));domains=list(csv.DictReader((D/'domain_service_round1.csv').open()));by=collections.defaultdict(list);rates=collections.defaultdict(list)
for v in clocks:
 key=(int(v['src']),int(v['dst']),int(v['descriptor']));rate=float(v['clock_ratio']);ns=float(v['global_ns']);assert round(ns*rate)==int(float(v['native_ticks']))
 assert rate in ([1,2.5] if 48 in key[:2] else [1]);by[key].append(ns);rates[key].append(rate)
grouped=collections.defaultdict(list)
for v in domains:grouped[(int(v['src']),int(v['dst']),int(v['descriptor']))].append(v)
for key,vs in grouped.items():
 assert len(by[key])==2*len(vs)
 for i,v in enumerate(vs):assert float(v['ready'])==math.ceil(max(by[key][2*i:2*i+2])) and sorted(rates[key][2*i:2*i+2])==([1,2.5] if 48 in key[:2] else [1,1])
assert len(clocks)==2*216755
out=dict(state='PASS_LIMITED_LOCAL_FULL_16NPU_PHASE1_REVIEW',members=160,stage_files=56,strict_output_KV_checks=12,CPU_outputs=2,matrix_calls=759,remote_matrices=450,host_parameter_fetches=61,clock_observations=len(clocks),NoC_phase2_and_round2_pending=True,full_steps_1_7=False)
(H/'LOCAL_PHASE1_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))

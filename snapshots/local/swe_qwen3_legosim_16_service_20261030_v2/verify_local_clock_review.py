import tarfile,json,hashlib,csv,collections,math
from pathlib import Path
H=Path(__file__).resolve().parent;pack=H/(H.name+'_REVIEW.tar.gz');review=H/'review';review.mkdir(exist_ok=True)
assert hashlib.sha256(pack.read_bytes()).hexdigest()=='d9db764a66f51b47d13252f28d7150f2d33292a407d8d97c9501e81ced9acba7'
with tarfile.open(pack) as t:
 assert all(not n.startswith('/') and '..' not in Path(n).parts for n in t.getnames());t.extractall(review,filter='data')
R=review/H.name
def j(p):return json.loads(p.read_text())
manifest=j(R/'MANIFEST.json');assert len(manifest)==381
for v in manifest:
 p=R/v['path'];assert p.stat().st_size==v['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==v['sha256']
for n,h in j(R/'FREEZE.json').items():assert hashlib.sha256((R/n).read_bytes()).hexdigest()==h
s=(H.parent/'swe_qwen3_legosim_16_service_20261030_v1/audit_local_review.py').read_text().replace('members=371',"members=len(j(R/'MANIFEST.json'))")
exec(compile(s,'prior_local_functional_audit','exec'),{'__file__':str(H/'prior_local_functional_audit.py')})
for iteration in [1,2]:
 clocks=list(csv.DictReader((R/'run1'/('clock_round%d.csv'%iteration)).open()));rows=list(csv.DictReader((R/('case%d'%iteration)/('domain_service_round%d.csv'%iteration)).open()));assert len(clocks)==11296
 by=collections.defaultdict(list);rates=collections.defaultdict(list)
 for v in clocks:
  key=(int(v['src']),int(v['dst']),int(v['descriptor']));rate=float(v['clock_ratio']);ns=float(v['global_ns']);assert round(ns*rate)==int(float(v['native_ticks']))
  assert rate in ([1,2.5] if 48 in key[:2] else [1]);by[key].append(ns);rates[key].append(rate)
 grouped=collections.defaultdict(list)
 for v in rows:grouped[(int(v['src']),int(v['dst']),int(v['descriptor']))].append(v)
 for key,vs in grouped.items():
  assert len(by[key])==2*len(vs)
  for i,v in enumerate(vs):assert float(v['ready'])==math.ceil(max(by[key][2*i:2*i+2])) and sorted(rates[key][2*i:2*i+2])==([1,2.5] if 48 in key[:2] else [1,1])
assert j(R/'CLOCK_AUDIT.json')['state']=='PASS_LIMITED_16_NODE_CLOCK_BINDING_CORRECTED'
out=dict(state='PASS_LIMITED_LOCAL_CLOCK_AND_16_NODE_REVIEW',members=381,rounds=2,clock_observations_each_round=11296,original_BF16=True,host_GiB=128,HB_GiB=8,full_steps_1_7=False,scope='corrected communication clock binding and finite16-gate data flows; full layer/opcode/CPU software/Bank costs not certified')
(H/'LOCAL_CLOCK_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))

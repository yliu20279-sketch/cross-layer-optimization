import json,hashlib,tarfile,types,sys,collections,csv
from pathlib import Path
H=Path(__file__).resolve().parent;R=H/'safe_review'/H.name
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(8*2**20):h.update(b)
 return h.hexdigest()
p=H/(H.name+'_SAFE_REVIEW.tar.gz');assert sha(p)=='a9f9c916059825f383ddadcdf72847b32769800f0c090588e0e25fbfcc98728e'
if not R.exists():
 with tarfile.open(p) as t:
  assert all(not n.startswith('/') and '..' not in Path(n).parts for n in t.getnames());t.extractall(H/'safe_review',filter='data')
manifest=json.loads((R/'SAFE_MANIFEST.json').read_text());assert len(manifest)==613
for v in manifest:assert (R/v['path']).stat().st_size==v['bytes'] and sha(R/v['path'])==v['sha256']
ref=H.parent/'swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1'
s=(R/'check_case.py').read_text();old="ref=B/'swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1'";assert old in s;s=s.replace(old,'ref=Path('+repr(str(ref))+')');mod=types.ModuleType('check_case');exec(compile(s,str(R/'check_case.py'),'exec'),mod.__dict__);sys.modules['check_case']=mod
s=(R/'audit_full.py').read_text();old="assert all(sha(Path(n))==h for n,h in j(R/'EXTERNAL_DEPENDENCIES.json').items())";assert old in s;s=s.replace(old,"external_dependencies_remote_only=j(R/'EXTERNAL_DEPENDENCIES.json')");s=s.replace("(R/'BASE_INDEPENDENT_AUDIT.json').write_text","(H/'LOCAL_BASE_AUDIT.json').write_text");exec(compile(s,str(R/'audit_full.py'),'exec'),dict(__file__=str(R/'audit_full.py'),H=H))
s=(R/'audit_clock.py').read_text().replace("runpy.run_path(str(R/'audit_full.py'))",'').replace("(R/'CLOCK_AUDIT.json')","(H/'LOCAL_CLOCK_AUDIT.json')");exec(compile(s,str(R/'audit_clock.py'),'exec'),dict(__file__=str(R/'audit_clock.py'),H=H))
# Keep frozen/extracted artifacts unchanged: redirect only the output of the independent validator.
s=(R/'validate_lowering.py').read_text().replace("(D/'LOWERING_AUDIT.json').write_text","(H/('LOCAL_LOWERING_ROUND%d.json'%iteration)).write_text");ns=dict(H=H);exec(compile(s,str(R/'validate_lowering.py'),'exec'),ns);summaries=[ns['validate'](R,i) for i in [1,2]]
oracle=json.loads((R/'oracle_cpu/RAW_MATRIX_ORACLE.json').read_text());assert len(oracle)==759
for iteration in [1,2]:
 D=R/('case%d'%iteration);g=[json.loads(s) for s in (D/'IMMEDIATE_FP32_GATES.jsonl').read_text().splitlines()];assert len(g)==759
 for i,v in enumerate(g):assert v['exact'] and v['actual_sha256']==v['expected_sha256']==oracle[i]['output_sha256'] and all(v[k]==oracle[i][k] for k in ['M','N','K'])
gaps=json.loads((R/'case1/LAYOUT_GAPS.json').read_text());counts=collections.Counter((v['label'],v['dtype']) for v in gaps)
out=dict(state='PASS_LIMITED_LOCAL_613_TWO_ROUND_REVIEW',members=613,rounds=summaries,FP32_elements_exact_per_round=sum(v['M']*v['N'] for v in oracle),external_binaries_and_full16GiB_table_rehashed_locally=False,full_steps_1_7=False,layout_gaps_by_label=[dict(label=k[0],dtype=k[1],count=n) for k,n in counts.items()])
(H/'LOCAL_SAFE_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))

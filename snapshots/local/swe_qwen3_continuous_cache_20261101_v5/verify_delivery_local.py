import sys,json,hashlib,tarfile,types,csv,sqlite3,collections,shutil
from pathlib import Path,PurePosixPath
from decimal import Decimal
H=Path(sys.argv[1]).resolve();R=H/'safe_review'/H.name;metadata=json.loads((H/'REMOTE_DELIVERY_STATUS.json').read_text());archive=H/(H.name+'_SAFE_REVIEW.tar.gz')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(8*1024**2):h.update(b)
 return h.hexdigest()
assert archive.stat().st_size==metadata['bytes'] and sha(archive)==metadata['sha256']
with tarfile.open(archive) as t:
 members=t.getmembers();assert len(members)<10000
 total=sum(m.size for m in members if m.isfile());assert total<16*1024**3
 if not R.exists():assert shutil.disk_usage(H).free>total+512*1024**2
 for m in members:
  path=PurePosixPath(m.name);assert not path.is_absolute() and path.parts[0]==H.name and '..' not in path.parts and m.isfile()
  p=H/'safe_review'/Path(*path.parts);p.parent.mkdir(parents=True,exist_ok=True)
  if p.exists():continue
  f=t.extractfile(m)
  with p.open('wb') as o:shutil.copyfileobj(f,o,8*1024**2)
manifest=json.loads((R/'SAFE_MANIFEST.json').read_text());assert len(manifest)==metadata['members']
for v in manifest:
 p=PurePosixPath(v['path']);assert not p.is_absolute() and '..' not in p.parts
 f=R/Path(*p.parts);assert f.stat().st_size==v['bytes'] and sha(f)==v['sha256'],v['path']
expected=json.loads((H/'EXPECTED_FREEZE.json').read_text());assert json.loads((R/'FREEZE.json').read_text())==expected
for n,h in expected.items():assert sha(R/n)==h,n
reference=H.parent/'swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1'
s=(R/'check_case.py').read_text();needle="ref=B/'swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1'";assert needle in s;s=s.replace(needle,'ref=Path('+repr(str(reference))+')');module=types.ModuleType('check_case');exec(compile(s,str(R/'check_case.py'),'exec'),module.__dict__);sys.modules['check_case']=module
s=(R/'audit_full.py').read_text();needle="assert all(sha(Path(n))==h for n,h in j(R/'EXTERNAL_DEPENDENCIES.json').items())";assert needle in s;s=s.replace(needle,"external_dependencies_rehashed_on113_only=j(R/'EXTERNAL_DEPENDENCIES.json')").replace("(R/'BASE_INDEPENDENT_AUDIT.json').write_text","(H/'LOCAL_BASE_AUDIT.json').write_text");exec(compile(s,str(R/'audit_full.py'),'exec'),dict(__file__=str(R/'audit_full.py'),H=H))
s=(R/'audit_clock.py').read_text().replace("runpy.run_path(str(R/'audit_full.py'))",'').replace("(R/'CLOCK_AUDIT.json')","(H/'LOCAL_CLOCK_AUDIT.json')");exec(compile(s,str(R/'audit_clock.py'),'exec'),dict(__file__=str(R/'audit_clock.py'),H=H))
s=(R/'validate_lowering.py').read_text().replace("(D/'LOWERING_AUDIT.json').write_text","(H/('LOCAL_LOWERING_ROUND%d.json'%iteration)).write_text");ns=dict(H=H);exec(compile(s,str(R/'validate_lowering.py'),'exec'),ns);lowerings=[ns['validate'](R,i) for i in [1,2]]
oracle=json.loads((R/'oracle_cpu/RAW_MATRIX_ORACLE.json').read_text());assert len(oracle)==759
cache=[]
for iteration in [1,2]:
 D=R/('case%d'%iteration);gates=[json.loads(s) for s in (D/'IMMEDIATE_FP32_GATES.jsonl').read_text().splitlines()];assert len(gates)==759
 for a,b in zip(gates,oracle):assert a['exact'] and a['actual_sha256']==a['expected_sha256']==b['output_sha256'] and all(a[k]==b[k] for k in ['M','N','K'])
 cpu_ticks=set()
 for row in csv.DictReader((R/'run1'/('clock_round%d.csv'%iteration)).open()):
  if Decimal(row['clock_ratio'])==Decimal('2.5'):cpu_ticks.add(int(Decimal(row['native_ticks'])))
 db=sqlite3.connect(str(D/'CPU_FINAL_STATS.sqlite3'));end=db.execute("select v.value from [values] v join names n using(nameid) join prefixes p using(prefixid) where n.objectname='performance_model' and n.metricname='elapsed_time' and v.core=0 and p.prefixname='roi-end'").fetchone()[0];db.close()
 source=(json.loads(s) for s in (D/'CPU_CACHE_GATES.jsonl').open());count=0
 for row in csv.DictReader((D/'CPU_CACHE_LEDGER.csv').open()):
  gate=next(source);count+=1
  for k in ['sequence','address','bytes']:assert int(row[k])==gate[k]
  assert row['kind']==gate['kind'] and gate['completed'] and int(row['sequence'])==count
  assert int(row['ack_prefix'])>=int(row['issued']) and int(row['ack_count'])==int(row['ack_prefix'])
  done=int(row['done_fs']);assert done>=int(row['now_fs']) and done>=int(row['max_ack_done_fs']) and int(row['final_CPU_elapsed_fs'])==end>=done
  tick=int(row['next_CPU_transport_ticks'])
  if tick>=0:assert tick in cpu_ticks and tick*400000>=done
 assert next(source,None) is None and count>0;cache.append(dict(round=iteration,cache_gates=count,final_CPU_elapsed_fs=end))
 if (R/'lifetime_adapter.py').exists():
  s=(R/'audit_control.py').read_text();needle="reference=B/'swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1'";assert needle in s;s=s.replace(needle,'reference=Path('+repr(str(reference))+')')
  needle="((D/'LIFETIME_AUDIT.json') if native else (R/'LIFETIME_CONTROL_AUDIT_V2.json')).write_text";assert needle in s;s=s.replace(needle,"(H/('LOCAL_LIFETIME_ROUND%d.json'%iteration)).write_text")
  saved=sys.argv;sys.argv=['audit_control.py','case%d'%iteration]
  try:exec(compile(s,str(R/'audit_control.py'),'exec'),dict(__file__=str(R/'audit_control.py'),H=H,iteration=iteration))
  finally:sys.argv=saved
out=dict(state='PASS_LIMITED_LOCAL_NUMERICAL_NOC_CLOCK_CACHE_REVIEW',members=len(manifest),archive_sha256=metadata['sha256'],rounds=lowerings,cache=cache,raw_CPU_ACK_logs_replayed_locally=False,external_binaries_and16GiB_table_rehashed_locally=False,dynamic_reclamation=(R/'lifetime_adapter.py').exists(),full_target_timing=False,full_steps_1_7=False)
(H/'LOCAL_FINAL_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))

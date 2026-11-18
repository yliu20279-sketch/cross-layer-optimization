"""Stage immutable L1/L2 sources and launch exactly one new bounded driver."""
import hashlib,io,json,shutil,subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parent
pkg=R/'package'
for name in ['driver.py','audit_priority.py']:
 shutil.copyfile(R/name,pkg/name)
s=json.loads((pkg/'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
for name in ['driver.py','audit_priority.py']:
 s.setdefault('support_sha256',{})[name]=hashlib.sha256((pkg/name).read_bytes()).hexdigest()
identity=hashlib.sha256(json.dumps(dict(source=s['source_sha256'],support=s['support_sha256']),sort_keys=True).encode()).hexdigest()[:16]
dest='/mnt/sdb1/h3240101068/dual_plane_priority_20261118/'+identity
s['deployment_id']=identity;s['remote_path']=dest
(pkg/'SOURCE_MANIFEST.json').write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8')
payload=io.BytesIO()
with tarfile.open(fileobj=payload,mode='w:gz') as tf:
 for p in sorted(pkg.rglob('*')):
  if p.is_file():tf.add(p,arcname=p.relative_to(pkg).as_posix())
archive=payload.getvalue();(R/'SOURCE_PACKAGE.tar.gz').write_bytes(archive)
script=r'''
import sys,pathlib,tarfile,io,json,hashlib,subprocess,os,time,re
dest=pathlib.Path(DESTINATION)
if dest.exists():
 print(json.dumps({'status':'EXISTING_DIRECTORY_NOT_RESTARTED','path':str(dest),'start':json.loads((dest/'START_AUTHORIZED.json').read_text()) if (dest/'START_AUTHORIZED.json').exists() else None}));sys.exit(0)
# Refuse to launch if another priority driver or result already exists nearby.
parent=dest.parent;parent.mkdir(parents=True,exist_ok=True)
others=[str(p) for p in parent.iterdir() if p.is_dir() and ((p/'START_AUTHORIZED.json').exists() or (p/'MATRIX.json').exists())]
allowed_predecessors=['3be6dbca32611f9c','ef3692791a4e77c9']
for old in others:
 previous=pathlib.Path(old)
 assert previous.name in allowed_predecessors and (previous/'FAILURE.json').exists() and not (previous/'MATRIX.json').exists(),('Existing L2 work requires inspection, not another start',old)
 # These two exact predecessors are retained bootstrap/probe failures with
 # different build/probe sources. Neither entered the 24-run experiment.
processes=subprocess.check_output(['ps','-eo','args'],text=True)
assert not any(re.match(r'^(?:\S*/)?python3(?: -u)? /mnt/\S*/dual_plane_priority_20261118/\S*/driver.py(?:\s|$)',line.strip()) for line in processes.splitlines()),'Existing priority driver detected'
raw=sys.stdin.buffer.read();assert hashlib.sha256(raw).hexdigest()==ARCHIVE_SHA
dest.mkdir(exist_ok=False)
with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tf:
 for member in tf.getmembers():
  path=pathlib.PurePosixPath(member.name);assert not path.is_absolute() and '..' not in path.parts and member.isfile()
  target=dest.joinpath(*path.parts);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(tf.extractfile(member).read())
s=json.loads((dest/'SOURCE_MANIFEST.json').read_text())
for name,expected in {**s['source_sha256'],**s['support_sha256']}.items():assert hashlib.sha256((dest/name).read_bytes()).hexdigest()==expected,name
cases=dest/'cases';cases.mkdir()
for case in s['cases']:
 raw=(pathlib.Path(s['baseline_root'])/'cases'/(case['name']+'.txt')).read_bytes()
 assert hashlib.sha256(raw).hexdigest()==case['case_sha256'];(cases/(case['name']+'.txt')).write_bytes(raw)
assert subprocess.check_output(['docker','image','inspect',s['image'],'--format','{{.Id}}'],text=True).strip()==s['image']
auth={'status':'AUTHORIZED_NEW_L1_L2_ONLY','time':time.time(),'source_digest':s['source_digest'],'deployment_id':s['deployment_id'],'tasks':24,'no_synthesis':True,'existing_312_runs_not_repeated':True,'worker_limit':8,'build_cpu_limit':4,'archive_sha256':ARCHIVE_SHA}
(dest/'START_AUTHORIZED.json').write_text(json.dumps(auth,indent=2))
log=(dest/'DRIVER.log').open('x')
p=subprocess.Popen(['python3','-u',str(dest/'driver.py')],cwd=dest,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,stdin=subprocess.DEVNULL)
auth['pid']=p.pid;(dest/'START_AUTHORIZED.json').write_text(json.dumps(auth,indent=2))
print(json.dumps({'status':'STARTED_NEW_PRIORITY_REGRESSION_THEN_24_RUNS','path':str(dest),'pid':p.pid,'authorization':auth}))
'''.replace('DESTINATION',repr(dest)).replace('ARCHIVE_SHA',repr(hashlib.sha256(archive).hexdigest()))
p=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=12','myserver-113','python3','-c',"'"+script.replace("'","'\\''")+"'"],input=archive,capture_output=True,timeout=60)
if p.returncode:
 (R/'DEPLOY_ERROR.txt').write_bytes(p.stderr);raise SystemExit(p.stderr.decode(errors='replace'))
d=json.loads(p.stdout);(R/'REMOTE_START.json').write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(d,ensure_ascii=False,indent=2))

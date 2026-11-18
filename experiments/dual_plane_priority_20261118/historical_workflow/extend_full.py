"""Authorize only L2 missing cases after verified precheck; no rebuild/synth."""
import hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent
pre=json.loads((R/'REMOTE_START.json').read_text(encoding='utf-8'))
snapshot=json.loads((R/'LATEST_STATUS.json').read_text(encoding='utf-8'))
assert json.loads(snapshot['files']['MATRIX.json'])['status']=='PASS'
assert json.loads((R/'INDEPENDENT_AUDIT.json').read_text(encoding='utf-8'))['status']=='PASS_COMPLETE_24'
old=json.loads((R.parent/'dual_plane_rtl_followup_20261118/REMOTE_SNAPSHOT.json').read_text(encoding='utf-8'))
driver=(R/'full_driver.py').read_text(encoding='utf-8')
audit=(R/'audit_priority.py').read_text(encoding='utf-8').replace("==24","==120").replace('PASS_L2_24_RUNS_144_PHASES','PASS_L2_120_RUNS_720_PHASES').replace('runs=24','runs=120')
# Future packages resolve the reused build explicitly. Do not modify the old
# immutable remote audit script or relaunch its already completed experiments.
audit=audit.replace("b=json.loads((R/'BUILD.json').read_text())", "b=json.loads((Path(json.loads((R/'EXTENSION_START.json').read_text())['precheck_path'])/'BUILD.json').read_text())")
identity=hashlib.sha256((driver+audit+pre['path']).encode()).hexdigest()[:16]
payload=dict(precheck_path=pre['path'],identity=identity,case_manifest_sha256=old['files']['CASES.json']['sha256'],driver=driver,audit=audit)
script=r'''
import pathlib,json,hashlib,subprocess,sys,time
d=json.loads(sys.stdin.buffer.read());p=pathlib.Path(d['precheck_path']);r=p.parent/('full_'+d['identity'])
if r.exists():print(json.dumps({'status':'EXISTING_EXTENSION_NOT_RESTARTED','path':str(r)}));sys.exit(0)
assert not list(p.parent.glob('full_*/EXTENSION_START.json')),'Another full L2 extension already exists'
old=json.loads((p/'MATRIX.json').read_text());src=json.loads((p/'SOURCE_MANIFEST.json').read_text())
assert old['status']=='PASS' and old['completed']==len(old['runs'])==24
assert json.loads((p/'AUDIT.json').read_text())['status'].startswith('PASS_L2_24')
raw=(pathlib.Path(src['baseline_root'])/'CASES.json').read_bytes();assert hashlib.sha256(raw).hexdigest()==d['case_manifest_sha256']
cases=json.loads(raw);assert len(cases)==30
arms=[('mesh',0,0),('hiband_FG',2,0),('hiband_GB',2,1),('hiband_LB',2,2)]
tasks=[dict(case=c['name'],arm=a,mode=m,hiband=h,bank=8,clock=1,policy='type_priority') for c in cases for a,m,h in arms]
done={(x['task']['case'],x['task']['arm']) for x in old['runs']};new=[t for t in tasks if (t['case'],t['arm']) not in done]
assert len(done)==24 and len(new)==96 and len(tasks)==120
r.mkdir();(r/'cases').mkdir();(r/'results').mkdir()
for c in cases:
 assert c['case_sha256']==src['baseline_matrix']['case_hashes'][c['name']]
 raw=(pathlib.Path(src['baseline_root'])/'cases'/(c['name']+'.txt')).read_bytes()
 assert hashlib.sha256(raw).hexdigest()==c['case_sha256'];(r/'cases'/(c['name']+'.txt')).write_bytes(raw)
for run in old['runs']:
 raw=(p/'results'/(run['name']+'.json')).read_bytes();assert hashlib.sha256(raw).hexdigest()==run['sha256']
 (r/'results'/(run['name']+'.json')).write_bytes(raw)
src['cases']=cases;src['extension_id']=d['identity'];(r/'SOURCE_MANIFEST.json').write_text(json.dumps(src,indent=2))
for name in ['rtl','sim','tests','obj0','obj1','obj2']:(r/name).symlink_to(p/name,target_is_directory=True)
(r/'driver.py').write_text(d['driver']);(r/'audit_full.py').write_text(d['audit'])
m=dict(status='ready',source_digest=src['source_digest'],image=src['image'],workers=8,tasks=tasks,runs=old['runs'],completed=24,new_completed=0,reused=24,new_scheduled=96,case_hashes={c['name']:c['case_sha256'] for c in cases})
(r/'MATRIX.json').write_text(json.dumps(m,indent=2))
auth=dict(status='AUTHORIZED_96_MISSING_L2_RUNS_REUSE_24',precheck_path=str(p),new_tasks=new,source_digest=src['source_digest'],identity=d['identity'],no_build=True,no_synthesis=True,started=time.time(),driver_sha256=hashlib.sha256(d['driver'].encode()).hexdigest(),audit_sha256=hashlib.sha256(d['audit'].encode()).hexdigest())
(r/'EXTENSION_START.json').write_text(json.dumps(auth,indent=2))
log=(r/'DRIVER.log').open('x');proc=subprocess.Popen(['python3','-u',str(r/'driver.py')],cwd=r,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
auth['pid']=proc.pid;(r/'EXTENSION_START.json').write_text(json.dumps(auth,indent=2))
print(json.dumps({'status':auth['status'],'path':str(r),'pid':proc.pid,'new_scheduled':96,'reused':24,'source_digest':src['source_digest'],'identity':d['identity']}))
'''
p=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=12','myserver-113','python3','-c',"'"+script.replace("'","'\\''")+"'"],input=json.dumps(payload).encode(),capture_output=True,timeout=60)
if p.returncode:raise SystemExit(p.stderr.decode(errors='replace'))
d=json.loads(p.stdout);(R/'FULL_EXTENSION_START.json').write_text(json.dumps(d,indent=2),encoding='utf-8');print(json.dumps(d,indent=2))

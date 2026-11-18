"""Bounded read-only polling of this chat's isolated L1/L2 run."""
import json,subprocess,datetime,argparse
from pathlib import Path
R=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--full',action='store_true');args=parser.parse_args()
start=json.loads((R/('FULL_EXTENSION_START.json' if args.full else 'REMOTE_START.json')).read_text(encoding='utf-8'))
script=r'''
import pathlib,json,datetime,subprocess,hashlib
r=pathlib.Path(REMOTE_PATH);out={'observed_at':datetime.datetime.now().astimezone().isoformat(),'remote_path':str(r),'files':{}}
build_root=pathlib.Path(json.loads((r/'EXTENSION_START.json').read_text())['precheck_path']) if (r/'EXTENSION_START.json').exists() else r
for name in ['START_AUTHORIZED.json','EXTENSION_START.json','BUILD.json','MATRIX.json','AUDIT.json','FAILURE.json','PAIRED_PHASES.csv','SOURCE_MANIFEST.json','UNIT_TEST.log','CONTROLLER_TEST.log']:
 p=r/name
 if name=='BUILD.json':p=build_root/name
 if p.exists():out['files'][name]=p.read_text()
for p in sorted(r.glob('SELFTEST_*.log')):out['files'][p.name]=p.read_text()
for p in [r/'DRIVER.log',*sorted(r.glob('UNIT_BUILD.log')),*sorted(r.glob('COMPILE_*.log'))]:
 if p.exists():out['files'][p.name]='\n'.join(p.read_text().splitlines()[-8:])
if (r/'MATRIX.json').exists():
 m=json.loads((r/'MATRIX.json').read_text());src=json.loads((r/'SOURCE_MANIFEST.json').read_text())
 out['results']={};out['rr_reference']={}
 for run in m.get('runs',[]):
  if run.get('status')!='PASS':continue
  p=r/'results'/(run['name']+'.json');raw=p.read_bytes()
  out['results'][run['name']]={'sha256':hashlib.sha256(raw).hexdigest(),'text':raw.decode()}
  t=run['task'];name=t['case']+'_'+t['arm']+'_b8'
  p=pathlib.Path(src['baseline_matrix']['result_path'])/(name+'.json');raw=p.read_bytes()
  out['rr_reference'][name]={'sha256':hashlib.sha256(raw).hexdigest(),'text':raw.decode()}
 out['binary_actual']={str(t['mode']):hashlib.sha256((r/f'obj{t["mode"]}/Vdut').read_bytes()).hexdigest() for t in json.loads((build_root/'BUILD.json').read_text())['targets']}
 out['source_actual']={name:hashlib.sha256((r/name).read_bytes()).hexdigest() for name in src['source_sha256']}
out['process']=subprocess.run(['ps','-p',str(PID),'-o','pid,ppid,etimes,args'],capture_output=True,text=True).stdout
print(json.dumps(out))
'''.replace('REMOTE_PATH',repr(start['path'])).replace('PID',str(start['pid']))
p=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=12','myserver-113','python3','-'],input=script.encode(),capture_output=True,timeout=45)
if p.returncode:raise SystemExit(p.stderr.decode(errors='replace'))
s=json.loads(p.stdout);(R/('FULL_LATEST_STATUS.json' if args.full else 'LATEST_STATUS.json')).write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8')
dest=R/'receipts'/Path(start['path']).name;dest.mkdir(parents=True,exist_ok=True)
for name,text in s['files'].items():(dest/name).write_text(text,encoding='utf-8')
print('Observed',s['observed_at']);print(s['process'])
for name in ['BUILD.json','MATRIX.json','AUDIT.json','FAILURE.json']:
 if name not in s['files']:continue
 d=json.loads(s['files'][name]);print(name,{k:d[k] for k in ['status','completed','error'] if k in d})
 if name=='BUILD.json':print('Built modes',[x['mode'] for x in d['targets']])
for name in ['UNIT_TEST.log','DRIVER.log','FAILURE.json']:
 if name in s['files']:print(name,s['files'][name][-2500:])

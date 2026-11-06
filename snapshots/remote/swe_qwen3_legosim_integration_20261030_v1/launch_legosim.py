"""Actual InterChiplet entry adapter; refuses incomplete integration receipts."""
import argparse,json,os,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('action',choices=['inspect','build-entry','launch']);p.add_argument('--contract',type=Path,default=R/'INTEGRATION_CONTRACT.json');args=p.parse_args()
c=json.loads(args.contract.read_text(encoding='utf-8'))
assert c['model_precision']=='BF16' and c['host_GiB']==128 and c['HB_GiB']==8 and c['target_GPU_count']==0
if args.action=='inspect':
 print(json.dumps(c,ensure_ascii=False,indent=2))
elif args.action=='build-entry':
 subprocess.run(['cmake','-S',str(R/'build_entry'),'-B',str(R/'build')],check=True)
 subprocess.run(['cmake','--build',str(R/'build'),'--parallel','2'],check=True)
else:
 missing=[k for k,v in c['acceptance'].items() if not v]
 if missing:raise SystemExit('Integration not ready: '+', '.join(missing))
 for key in ['simulator_root','phase_yaml','fresh_run_directory']:
  if not c.get(key):raise SystemExit('Missing binding: '+key)
 sim=Path(c['simulator_root']).resolve();yaml=Path(c['phase_yaml']).resolve();run=Path(c['fresh_run_directory']).resolve();binary=R/'build/interchiplet'
 if not yaml.is_file() or not binary.is_file():raise SystemExit('Missing actual entry/YAML')
 run.mkdir(parents=True,exist_ok=False)
 env=dict(os.environ,SIMULATOR_ROOT=str(sim),BENCHMARK_ROOT=str(R))
 with (run/'interchiplet.log').open('w') as out:
  subprocess.run([str(binary),str(yaml),'-w',str(c['mesh_width']),'-f','4','-t',str(c['feedback_rounds'])],cwd=run,env=env,stdout=out,stderr=subprocess.STDOUT,check=True,timeout=1200)

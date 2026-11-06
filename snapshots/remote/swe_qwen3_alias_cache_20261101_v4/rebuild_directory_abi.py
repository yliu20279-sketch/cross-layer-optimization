import json,shutil,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent;S=R/'sniper_drain_candidate'
for n in ['DRAIN_BUILD_EXIT.json','DRAIN_BUILD_V2.log']:shutil.copy2(R/n,R/('BEFORE_FULL_ABI_'+n))
n=0
for folder in ['common','standalone']:
 for p in (S/folder).rglob('*.d'):
  s=p.read_text();new=s
  for old in ['/workspace/sim/snipersim','/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/snipersim']:new=new.replace(old,str(S))
  if new!=s:p.write_text(new);n+=1
(R/'ABI_REBUILD_METHOD.json').write_text(json.dumps(dict(state='FULL_REBUILD_REQUIRED_NOT_PASS',dependency_files_fixed=n,reason='native parent GDB found heap corruption; copied .d files still target /workspace/sim/snipersim; changed ShmemMsg ABI requires all common objects rebuilt',original_source_unchanged=True,started=time.time()),indent=2))
with (R/'DIRECTORY_FULL_ABI_BUILD.log').open('w') as f:p=subprocess.Popen(['python3',str(R/'build_drain.py'),'--force'],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps(dict(dependencies_fixed=n,build_pid=p.pid)))

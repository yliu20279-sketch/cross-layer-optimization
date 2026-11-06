import json,subprocess,shutil,os,time
from pathlib import Path
R=Path(__file__).resolve().parent;p=R/'sniper_drain_candidate/common/core/memory_subsystem/parametric_dram_directory_msi/cache_cntlr.cc'
s=p.read_text(encoding='utf-8-sig');assert '#include "software_maintenance_tracker.h"' not in s
p.write_text('#include "software_maintenance_tracker.h"\n'+s)
for n in ['DRAIN_BUILD_EXIT.json','DRAIN_BUILD_V2.log','DIRECTORY_FINISH_STATUS.json','REVIEW_DELIVERY_STATUS.json']:
 if (R/n).exists():shutil.copy2(R/n,R/('FAILED_TRACKER_INCLUDE_'+n))
with (R/'DIRECTORY_FULL_ABI_FINAL_BUILD.log').open('w') as f:b=subprocess.Popen(['python3',str(R/'build_drain.py'),'--force'],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
(R/'FINAL_BUILD_PID.json').write_text(json.dumps(dict(pid=b.pid,started=time.time(),bound_seconds=1200,reason='explicit missing tracker include corrected; full ABI rebuild retained'),indent=2))
env=os.environ.copy();env.update(SWE_BUILD_PID=str(b.pid),SWE_REVIEW_SUFFIX='_retry1')
with (R/'DIRECTORY_FINISH_RETRY1.log').open('w') as f:q=subprocess.Popen(['python3',str(R/'finish_directory_probe.py')],stdout=f,stderr=subprocess.STDOUT,start_new_session=True,env=env)
print(json.dumps(dict(build_pid=b.pid,finish_pid=q.pid)))

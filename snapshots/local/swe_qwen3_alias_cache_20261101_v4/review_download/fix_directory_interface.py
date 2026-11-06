import shutil,subprocess,json
from pathlib import Path
R=Path(__file__).resolve().parent;P=R/'sniper_drain_candidate/common/core/memory_subsystem'
for n in ['DRAIN_BUILD_EXIT.json','DRAIN_BUILD_V2.log']:shutil.copy2(R/n,R/('FAILED_DIRECTORY_INTERFACE_'+n))
for name in ['memory_manager_base.h','memory_manager_fast.h']:
 p=P/name;s=p.read_text();lines=s.splitlines();found=0
 for i,line in enumerate(lines):
  if 'void sendMsg(' in line:
   needle='ShmemPerfModel::Thread_t thread_num = ShmemPerfModel::NUM_CORE_THREADS)';assert needle in line
   lines[i]=line.replace(needle,'ShmemPerfModel::Thread_t thread_num = ShmemPerfModel::NUM_CORE_THREADS, UInt64 maintenance_token = 0)');found+=1
 assert found==1;p.write_text('\n'.join(lines)+'\n')
with (R/'DIRECTORY_BUILD_INTERFACE.log').open('w') as f:p=subprocess.Popen(['python3',str(R/'build_drain.py')],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps(dict(state='REBUILD_STARTED_NOT_PASS',pid=p.pid)))

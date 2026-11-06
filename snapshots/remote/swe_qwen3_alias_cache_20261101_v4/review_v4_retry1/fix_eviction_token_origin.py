import os,signal,json,subprocess,shutil
from pathlib import Path
R=Path(__file__).resolve().parent;S=R/'sniper_drain_candidate';M=S/'common/core/memory_subsystem/parametric_dram_directory_msi'
pid=2088867;p=Path('/proc/%d/cmdline'%pid)
if p.exists():
 args=p.read_bytes();assert b'build_drain.py' in args and b'--force' in args;assert os.getpgid(pid)==pid;os.killpg(pid,signal.SIGKILL)
shutil.copy2(R/'DRAIN_BUILD_V2.log',R/'STOPPED_FOR_EXPLICIT_EVICTION_TOKEN_BUILD.log')
p=M/'memory_manager.cc';s=p.read_text();a=s.index('   if (m_enabled && msg_type == PrL1PrL2DramDirectoryMSI::ShmemMsg::FLUSH_REP');b=s.index('   shmem_msg.setMaintenanceToken(maintenance_token);',a);s=s[:a]+s[b:];p.write_text(s)
p=M/'cache_cntlr.cc';s=p.read_text().replace('#include "cache_cntlr.h"','#include "cache_cntlr.h"\n#include "software_maintenance_tracker.h"');a=s.index('MYLOG("evict FLUSH %lx", evict_address);');b=s.index('\n         }',a);part=s[a:b];needle='&m_dummy_shmem_perf, thread_num);';assert part.count(needle)==1
part=part.replace(needle,'&m_dummy_shmem_perf, thread_num, SoftwareMaintenanceTracker::instance().issue(evict_address));');s=s[:a]+part+s[b:];p.write_text(s)
(R/'EVICTION_TOKEN_METHOD.json').write_text(json.dumps(dict(state='PREREGISTERED_NOT_PASS',method='tag at voluntary dirty eviction call site, independent of user/sim callback thread; do not tag unrelated coherence replies',other_active_CPUs=False),indent=2))
with (R/'DIRECTORY_FULL_ABI_BUILD_V2.log').open('w') as f:p=subprocess.Popen(['python3',str(R/'build_drain.py'),'--force'],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps(dict(build_pid=p.pid)))

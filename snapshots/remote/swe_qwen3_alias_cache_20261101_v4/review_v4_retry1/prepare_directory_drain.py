"""Instrument real directory write completion in isolated candidate only."""
import json,shutil,subprocess,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;S=R/'sniper_drain_candidate';C=S/'common';P=C/'core/memory_subsystem';M=P/'parametric_dram_directory_msi';T=P/'pr_l1_pr_l2_dram_directory_msi'
backup=R/'direct_queue_candidate_source';backup.mkdir(exist_ok=False)
for p in [M/'memory_manager.h',M/'memory_manager.cc',M/'cache_cntlr.h',M/'cache_cntlr.cc',C/'system/magic_server.cc']:
 q=backup/p.relative_to(C);q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
for n in ['DRAIN_BUILD_EXIT.json','DRAIN_PROBE_EXIT.json','DRAIN_PROBE.log']:
 shutil.copy2(R/n,backup/n)
(C/'system/software_maintenance_tracker.h').write_text(r'''#pragma once
#include <mutex>
#include <condition_variable>
#include <chrono>
#include <map>
#include <cstdio>
#include "subsecond_time.h"
#include "log.h"
// Simulator-only transaction IDs, not architecture payload or guessed latency.
class SoftwareMaintenanceTracker {
 std::mutex mutex;std::condition_variable cv;
 UInt64 next=0;std::map<UInt64,IntPtr> pending;SubsecondTime latest=SubsecondTime::Zero();
public:
 static SoftwareMaintenanceTracker& instance(){static SoftwareMaintenanceTracker t;return t;}
 UInt64 issue(IntPtr address){std::lock_guard<std::mutex> l(mutex);UInt64 id=++next;pending[id]=address;return id;}
 void complete(UInt64 id,IntPtr address,SubsecondTime start,SubsecondTime done){
  std::lock_guard<std::mutex> l(mutex);auto it=pending.find(id);
  LOG_ASSERT_ERROR(it!=pending.end() && it->second==address,"unmatched directory maintenance completion");
  LOG_ASSERT_ERROR(done>=start,"negative directory write latency");
  pending.erase(it);if(done>latest)latest=done;
  fprintf(stderr,"MAINT_WRITE_ACK %llu %llu %llu %llu\n",(unsigned long long)id,(unsigned long long)address,(unsigned long long)start.getFS(),(unsigned long long)done.getFS());cv.notify_all();
 }
 SubsecondTime drain(SubsecondTime now){std::unique_lock<std::mutex> l(mutex);UInt64 issued=next;
  bool ready=cv.wait_for(l,std::chrono::seconds(10),[this]{return pending.empty();});
  LOG_ASSERT_ERROR(ready,"directory maintenance timed out with unacknowledged writes");
  SubsecondTime done=latest>now?latest:now;
  fprintf(stderr,"MAINT_DRAIN %llu %llu %llu %llu\n",(unsigned long long)issued,(unsigned long long)pending.size(),(unsigned long long)now.getFS(),(unsigned long long)done.getFS());return done;
 }
};
''')
# Token is copied by existing sizeof(ShmemMsg) transport serialization.
p=T/'shmem_msg.h';s=p.read_text().replace('         ShmemPerf* m_perf;','         ShmemPerf* m_perf;\n         UInt64 m_maintenance_token = 0;');needle='         void setWhere(HitWhere::where_t where) { m_where = where; }';assert needle in s
s=s.replace(needle,needle+'\n         UInt64 getMaintenanceToken() const { return m_maintenance_token; }\n         void setMaintenanceToken(UInt64 token) { m_maintenance_token = token; }');p.write_text(s)
p=T/'shmem_msg.cc';s=p.read_text().replace('      m_perf(shmem_msg->getPerf())','      m_perf(shmem_msg->getPerf()),\n      m_maintenance_token(shmem_msg->getMaintenanceToken())');p.write_text(s)
p=M/'memory_manager.h';s=p.read_text();needle='ShmemPerfModel::Thread_t thread_num = ShmemPerfModel::NUM_CORE_THREADS);';assert s.count(needle)==4
# Change only sendMsg, not broadcastMsg.
lines=s.splitlines();lines=[x.replace(needle,'ShmemPerfModel::Thread_t thread_num = ShmemPerfModel::NUM_CORE_THREADS, UInt64 maintenance_token = 0);') if 'void sendMsg(' in x else x for x in lines];p.write_text('\n'.join(lines)+'\n')
p=M/'memory_manager.cc';s=p.read_text().replace('#include "core_manager.h"','#include "software_maintenance_tracker.h"\n#include "core_manager.h"');s=s.replace('return m_cache_cntlrs[m_last_level_cache]->drainWritebacksForSoftwareMaintenance(now);','return SoftwareMaintenanceTracker::instance().drain(now);')
needle='ShmemPerf *perf, ShmemPerfModel::Thread_t thread_num)\n{\nMYLOG("send msg';assert needle in s
s=s.replace(needle,'ShmemPerf *perf, ShmemPerfModel::Thread_t thread_num, UInt64 maintenance_token)\n{\nMYLOG("send msg')
needle='   shmem_msg.setWhere(where);';assert s.count(needle)==1
s=s.replace(needle,needle+'''
   if (m_enabled && msg_type == PrL1PrL2DramDirectoryMSI::ShmemMsg::FLUSH_REP && thread_num == ShmemPerfModel::_USER_THREAD) {
      LOG_ASSERT_ERROR(requester == 0 && maintenance_token == 0, "maintenance protocol supports CPU0 only");
      maintenance_token = SoftwareMaintenanceTracker::instance().issue(address);
   }
   shmem_msg.setMaintenanceToken(maintenance_token);
''');p.write_text(s)
p=T/'dram_directory_cntlr.h';s=p.read_text().replace('void sendDataToDram(IntPtr address, core_id_t requester, Byte* data_buf, SubsecondTime now);','void sendDataToDram(IntPtr address, core_id_t requester, Byte* data_buf, SubsecondTime now, UInt64 maintenance_token = 0);');p.write_text(s)
p=T/'dram_directory_cntlr.cc';s=p.read_text();a=s.index('DramDirectoryCntlr::processFlushRepFromL2Cache(');b=s.index('\nvoid\n',a)
part=s[a:b];needle='   if (m_dram_directory_req_queue_list->size(address) != 0)';assert needle in part
part=part.replace(needle,'   LOG_ASSERT_ERROR(!shmem_msg->getMaintenanceToken() || (!m_nuca_cache && m_dram_directory_req_queue_list->size(address) == 0), "maintenance write collided with active directory request or NUCA");\n'+needle)
part=part.replace('sendDataToDram(address, shmem_msg->getRequester(), shmem_msg->getDataBuf(), now);','sendDataToDram(address, shmem_msg->getRequester(), shmem_msg->getDataBuf(), now, shmem_msg->getMaintenanceToken());');s=s[:a]+part+s[b:]
s=s.replace('DramDirectoryCntlr::sendDataToDram(IntPtr address, core_id_t requester, Byte* data_buf, SubsecondTime now)','DramDirectoryCntlr::sendDataToDram(IntPtr address, core_id_t requester, Byte* data_buf, SubsecondTime now, UInt64 maintenance_token)')
a=s.index('DramDirectoryCntlr::sendDataToDram(');part=s[a:];needle='ShmemPerfModel::_SIM_THREAD);';assert part.count(needle)==1;part=part.replace(needle,'ShmemPerfModel::_SIM_THREAD, maintenance_token);');s=s[:a]+part;p.write_text(s)
p=P/'dram/dram_cntlr_interface.cc';s=p.read_text().replace('#include "dram_cntlr_interface.h"','#include "software_maintenance_tracker.h"\n#include "dram_cntlr_interface.h"');needle='         putDataToDram(shmem_msg->getAddress(), shmem_msg->getRequester(), shmem_msg->getDataBuf(), msg_time);';assert needle in s
s=s.replace(needle,'''         SubsecondTime latency; HitWhere::where_t where;
         boost::tie(latency, where) = putDataToDram(shmem_msg->getAddress(), shmem_msg->getRequester(), shmem_msg->getDataBuf(), msg_time);
         if (shmem_msg->getMaintenanceToken()) SoftwareMaintenanceTracker::instance().complete(shmem_msg->getMaintenanceToken(), shmem_msg->getAddress(), msg_time, msg_time + latency);''');p.write_text(s)
changed=[C/'system/software_maintenance_tracker.h',M/'memory_manager.h',M/'memory_manager.cc',T/'shmem_msg.h',T/'shmem_msg.cc',T/'dram_directory_cntlr.h',T/'dram_directory_cntlr.cc',P/'dram/dram_cntlr_interface.cc',C/'system/magic_server.cc']
(R/'DIRECTORY_DRAIN_METHOD.json').write_text(json.dumps(dict(state='CANDIDATE_NOT_CERTIFIED',method='unique simulator transaction token from CPU0 voluntary dirty eviction through actual directory DRAM_WRITE_REQ; acknowledge actual putDataToDram latency; synchronize CPU to latest completed write',rejects=['active directory request conflict','NUCA','other active CPU','missing completion after10s wall watchdog'],changed_sha256={str(p.relative_to(S)):hashlib.sha256(p.read_bytes()).hexdigest() for p in changed},native_full_layer_runs=0),indent=2))
with (R/'DIRECTORY_BUILD_SUPERVISOR.log').open('w') as f:p=subprocess.Popen(['python3',str(R/'build_drain.py')],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps(dict(state='DIRECTORY_CANDIDATE_BUILD_STARTED',pid=p.pid)))

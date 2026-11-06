"""Prepare isolated Sniper queue-drain candidate, never edit shared source."""
import hashlib,json,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent
S=Path('/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/snipersim')
D=R/'sniper_drain_candidate'
assert not D.exists(), 'preserve previous candidate'
subprocess.run(['cp','-a','--reflink=auto',str(S),str(D)],check=True)
names=['common/system/magic_server.cc','common/core/memory_subsystem/parametric_dram_directory_msi/memory_manager.h','common/core/memory_subsystem/parametric_dram_directory_msi/memory_manager.cc']
original={n:hashlib.sha256((S/n).read_bytes()).hexdigest() for n in names}
p=D/names[1];s=p.read_text();needle='         MemoryManager(Core* core, Network* network, ShmemPerfModel* shmem_perf_model);';assert needle in s
s=s.replace(needle,needle+'\n         SubsecondTime drainWritebacksForSoftwareMaintenance(SubsecondTime now);');p.write_text(s)
p=D/names[2];s=p.read_text();needle='std::map<CoreComponentType, CacheCntlr*> MemoryManager::m_all_cache_cntlrs;';assert needle in s
s=s.replace(needle,needle+'''

// Called only after explicit ordinary-load eviction of the DMA range.
// This drains the existing modeled queue, and does not implement CLFLUSH.
SubsecondTime MemoryManager::drainWritebacksForSoftwareMaintenance(SubsecondTime now)
{
   CacheCntlr* llc = m_cache_cntlrs[m_last_level_cache];
   ScopedLock sl(llc->getLock());
   LOG_ASSERT_ERROR(llc->m_master->m_dram_cntlr && llc->m_master->m_dram_outstanding_writebacks,
      "software maintenance requires direct DRAM and tracked writebacks");
   return llc->m_master->m_dram_outstanding_writebacks->getBarrierCompletionTime(now, SubsecondTime::Zero());
}
''');p.write_text(s)
p=D/names[0];s=p.read_text();s=s.replace('#include "thread.h"','#include "thread.h"\n#include "memory_manager.h"\n#include "instruction.h"\n#include "shmem_perf_model.h"')
needle='      case SIM_CMD_USER:\n      {';assert needle in s
s=s.replace(needle,needle+'''
         if (arg0 == 0x534d4344ULL) {
            LOG_ASSERT_ERROR(core_id == 0 && arg1 == 0x445241494eULL,
               "software maintenance drain restricted to preregistered CPU0 protocol");
            Core* core = Sim()->getCoreManager()->getCoreFromID(core_id);
            ParametricDramDirectoryMSI::MemoryManager* mm = dynamic_cast<ParametricDramDirectoryMSI::MemoryManager*>(core->getMemoryManager());
            LOG_ASSERT_ERROR(mm, "unsupported memory manager for software maintenance");
            SubsecondTime now = core->getPerformanceModel()->getElapsedTime();
            SubsecondTime memory_now = core->getShmemPerfModel()->getElapsedTime(ShmemPerfModel::_USER_THREAD);
            if (memory_now > now) now = memory_now;
            SubsecondTime done = mm->drainWritebacksForSoftwareMaintenance(now);
            core->getShmemPerfModel()->updateElapsedTime(done, ShmemPerfModel::_USER_THREAD);
            core->getPerformanceModel()->queuePseudoInstruction(new SyncInstruction(done, SyncInstruction::PTHREAD_BARRIER));
            return 0x534d4344ULL;
         }
''');p.write_text(s)
manifest=dict(state='CANDIDATE_NOT_CERTIFIED',source=str(S),candidate=str(D),original_sha256=original,changed_sha256={n:hashlib.sha256((D/n).read_bytes()).hexdigest() for n in names},method='explicit software LRU eviction then existing queue getBarrierCompletionTime(now,zero), CPU synchronization to actual queued completion; no fixed latency',limits=['CPU0 only, other cores idle','must validate queue drained and time gate before native full layers','not native CLFLUSH or physical cache certification'])
(R/'DRAIN_HOOK_METHOD.json').write_text(json.dumps(manifest,indent=2))
cmd=['/usr/bin/timeout','1200','make','-j4','-C',str(D),'compile_simulator']
with (R/'DRAIN_BUILD.log').open('w') as f:
 p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
(R/'DRAIN_BUILD_PID.json').write_text(json.dumps(dict(pid=p.pid,command=cmd,started=time.time())))
print(json.dumps(dict(state='BUILD_STARTED_NOT_PASS',pid=p.pid)))

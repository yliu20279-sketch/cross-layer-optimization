import json,hashlib,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;S=R/'sniper_drain_candidate';P=S/'common/core/memory_subsystem/parametric_dram_directory_msi'
for n in ['DRAIN_BUILD_V2.log','DRAIN_BUILD_EXIT.json']:
 shutil.copy2(R/n,R/('FAILED_INITIAL_'+n))
p=P/'memory_manager.cc';s=p.read_text();a=s.index('   CacheCntlr* llc = m_cache_cntlrs[m_last_level_cache];');b=s.index('\n}',a)
s=s[:a]+'   return m_cache_cntlrs[m_last_level_cache]->drainWritebacksForSoftwareMaintenance(now);'+s[b:];p.write_text(s)
p=P/'cache_cntlr.h';s=p.read_text();needle='         Cache* getCache() { return m_master->m_cache; }';assert needle in s;s=s.replace(needle,needle+'\n         SubsecondTime drainWritebacksForSoftwareMaintenance(SubsecondTime now);');p.write_text(s)
p=P/'cache_cntlr.cc';s=p.read_text();needle='namespace ParametricDramDirectoryMSI\n{';assert needle in s
s=s.replace(needle,needle+'''

SubsecondTime CacheCntlr::drainWritebacksForSoftwareMaintenance(SubsecondTime now)
{
   ScopedLock sl(getLock());
   LOG_ASSERT_ERROR(m_master->m_dram_cntlr && m_master->m_dram_outstanding_writebacks,
      "software maintenance requires direct DRAM and tracked writebacks");
   SubsecondTime done = m_master->m_dram_outstanding_writebacks->getBarrierCompletionTime(now, SubsecondTime::Zero());
   LOG_ASSERT_ERROR(m_master->m_dram_outstanding_writebacks->getNumUsed(done) == 0,
      "writeback queue not empty at reported completion");
   return done;
}
''');p.write_text(s)
with (R/'DRAIN_BUILD_SUPERVISOR_V3.log').open('w') as f:
 p=subprocess.Popen(['python3',str(R/'build_drain.py')],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps(dict(state='REBUILD_STARTED_NOT_PASS',pid=p.pid)))

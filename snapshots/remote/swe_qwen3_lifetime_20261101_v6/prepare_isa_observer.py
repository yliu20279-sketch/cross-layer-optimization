"""Observe all SIFT-decoded x86 instructions using the bundled XED chip check."""
import json,hashlib,subprocess,os
from pathlib import Path
R=Path(__file__).resolve().parent;V4=R.parent/'swe_qwen3_alias_cache_20261101_v4';old=V4/'sniper_drain_candidate';S=R/'sniper_isa_candidate';assert not S.exists()
subprocess.run(['cp','-a','--reflink=auto',str(old),str(S)],check=True)
dependency=R/'interchiplet'
if not dependency.exists():os.symlink('/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/interchiplet',str(dependency),target_is_directory=True)
count=0
for folder in ['common','standalone']:
 for p in (S/folder).rglob('*.d'):
  s=p.read_text();n=s.replace(str(old),str(S)).replace('/workspace/sim/snipersim',str(S))
  if n!=s:p.write_text(n);count+=1
p=S/'common/trace_frontend/trace_thread.cc';s=p.read_text();original=hashlib.sha256(p.read_bytes()).hexdigest()
s=s.replace('#include "stats.h"','#include "stats.h"\n#include <map>\n#include <tuple>\n#include <mutex>')
needle='   instruction->setDisassembly(dec_inst.disassembly_to_str().c_str());';assert needle in s
s=s.replace(needle,needle+'''
   // Observer only: no arithmetic, target timing, opcode lowering or payload changes.
   // All real SIFT instructions are decoded on this path before execution.
   {
      const dl::X86DecodedInst* x86 = dynamic_cast<const dl::X86DecodedInst*>(&dec_inst);
      LOG_ASSERT_ERROR(x86, "Nehalem ISA observer requires x86 decoder");
      xed_decoded_inst_t* xed = const_cast<dl::X86DecodedInst*>(x86)->get_xed_inst();
      bool supported = xed_decoded_inst_valid_for_chip(xed, XED_CHIP_NEHALEM);
      String name = String(xed_isa_set_enum_t2str(xed_decoded_inst_get_isa_set(xed))) + "_" + xed_iclass_enum_t2str(xed_decoded_inst_get_iclass(xed));
      typedef std::tuple<core_id_t, String, bool> Key;
      static std::map<Key, UInt64> counters;
      static std::mutex mutex;
      std::lock_guard<std::mutex> lock(mutex);
      core_id_t core = m_thread->getCore()->getId();
      auto value = counters.insert(std::make_pair(Key(core,name,supported),UInt64(0)));
      if(value.second) registerStatsMetric(supported ? "decoded_isa_nehalem_ok" : "decoded_isa_nehalem_rejected",core,name,&value.first->second);
      ++value.first->second;
   }
''');p.write_text(s)
(R/'ISA_OBSERVER_METHOD.json').write_text(json.dumps(dict(state='CANDIDATE_NOT_READY',source=str(old),candidate=str(S),original_trace_source_sha256=original,observer_trace_source_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),dependencies_rebased=count,method='bundled XED valid_for_chip(NEHALEM) for every SIFT decoded instruction before execution; includes dynamically dispatched libraries; counters are decoded occurrences, not full dynamic instruction frequency',arithmetic_or_simulated_clock_changes=False,full_steps_1_7=False),indent=2))
with (R/'ISA_OBSERVER_BUILD.log').open('w') as f:
 rows=[]
 for folder in ['common','standalone']:
  cmd=['make','-j4','-C',str(S/folder)];c=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=1200);rows.append(dict(command=cmd,returncode=c.returncode))
  if c.returncode:break
state=dict(state='BUILD_ONLY_NOT_ISA_PASS' if len(rows)==2 and not any(v['returncode'] for v in rows) else 'BUILD_FAILED',commands=rows)
if state['state']=='BUILD_ONLY_NOT_ISA_PASS':state['binary_sha256']=hashlib.sha256((S/'lib/sniper').read_bytes()).hexdigest()
(R/'ISA_OBSERVER_BUILD_EXIT.json').write_text(json.dumps(state,indent=2));print(json.dumps(state))

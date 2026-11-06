import shutil,subprocess,json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;V=R.parent/'swe_qwen3_legosim_16_service_20261030_v1';S=R/'source/interchiplet'
shutil.copytree(V/'source/interchiplet',S)
s=(V/'domain_service.h').read_text().replace('#include <fstream>','#include <fstream>\n#include <iomanip>')
s=s.replace('std::ofstream log,feedback_log;', 'std::ofstream log,feedback_log,clock_log;')
s=s.replace('s.feedback_log<<"src,dst,descriptor,writer_ready,reader_ready,profile_applied\\n";', 's.feedback_log<<std::setprecision(17)<<"src,dst,descriptor,writer_ready,reader_ready,profile_applied\\n";s.log<<std::setprecision(17);if(s.clock_log.is_open())s.clock_log.close();s.clock_log.open("clock_round"+std::to_string(s.round)+".csv");s.clock_log<<std::setprecision(17)<<"src,dst,descriptor,native_ticks,clock_ratio,global_ns\\n";')
s=s.replace('double ready=std::max(w.m_cycle,r.m_cycle)', 'double ready=std::ceil(std::max(w.m_cycle,r.m_cycle))')
assert 'ready=std::ceil' in s and 'clock_round' in s
pos=s.index('inline double complete(')
extra='''inline InterChiplet::TimeType tick(double value){return static_cast<InterChiplet::TimeType>(enabled()?std::ceil(value):value);}
inline void observe_clock(const InterChiplet::SyncCommand&c,double native){if(enabled()&&(c.m_type==InterChiplet::SC_READ||c.m_type==InterChiplet::SC_WRITE)){auto&s=state();s.clock_log<<id(c.m_src)<<','<<id(c.m_dst)<<','<<c.m_desc<<','<<native<<','<<c.m_clock_rate<<','<<c.m_cycle<<'\\n';s.clock_log.flush();}}
'''
s=s[:pos]+extra+s[pos:];(R/'domain_service.h').write_text(s);(S/'includes/domain_service.h').write_text(s)
p=S/'srcs/cmd_handler.cpp';s=p.read_text();assert s.count('static_cast<InterChiplet::TimeType>(')>4;s=s.replace('static_cast<InterChiplet::TimeType>(', 'swe_domain::tick(');p.write_text(s)
s=(V/'interchiplet.cpp').read_text();needle='cmd.m_cycle = cmd.m_cycle / __proc_struct->m_clock_rate;';assert s.count(needle)==1
s=s.replace(needle,'const double swe_native_ticks = cmd.m_cycle;\n            '+needle)
needle='pthread_mutex_lock(&__proc_struct->m_sync_struct->m_mutex);';assert s.count(needle)==1
s=s.replace(needle,needle+'\n            swe_domain::observe_clock(cmd,swe_native_ticks);');(R/'interchiplet.cpp').write_text(s)
cm=(V/'CMakeLists.txt').read_text().replace(str(V/'interchiplet.cpp'),str(R/'interchiplet.cpp'));(R/'CMakeLists.txt').write_text(cm)
for cmd in [['cmake','-S',str(R),'-B',str(R/'build'),'-DCMAKE_BUILD_TYPE=Release'],['cmake','--build',str(R/'build'),'-j','4']]:
 with (R/'BUILD.log').open('a') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
paths=[Path('/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/snipersim/common/core/syscall_model.cc'),Path('/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/snipersim/common/system/dvfs_manager.cc'),Path('/mnt/sdb1/h3240101068/npusim_ramulator2_validation_20260826/workspace/Ramulator2-Chiplet/ramulator2_wrapper.cpp'),Path('/mnt/sdb1/h3240101068/npusim_ramulator2_validation_20260826/workspace/Ramulator2-Chiplet/main.cpp')]
out=dict(state='BUILT_CLOCK_FIX_NOT_YET_RUNTIME_CERTIFIED',CPU_native_tick_ns=0.4,CPU_process_clock_rate=2.5,global_unit_ns=1,NPU_process_clock_rate=1,NoC_process_clock_rate=1,DRAM_native_tick_ns=1.25,DRAM_server_cycle_scale=1.25,boundary_policy='ceil to receiving tick; service ready ceil to1ns; no completion before arrival',sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},binary_sha256=hashlib.sha256((R/'build/interchiplet').read_bytes()).hexdigest())
(R/'BINDING.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))

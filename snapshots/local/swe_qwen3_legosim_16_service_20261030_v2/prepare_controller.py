import shutil,subprocess,json,hashlib
from pathlib import Path
B=Path('/mnt/sda1/h3240101068');OLD=B/'swe_qwen3_legosim_integration_20261030_v1';R=B/'swe_qwen3_legosim_16_service_20261030_v1'
S=R/'source/interchiplet';shutil.copytree(OLD/'source/interchiplet',S)
shutil.copy2(R/'domain_service.h',S/'includes/domain_service.h')
p=S/'includes/net_delay.h';s=p.read_text().replace('#include "global_define.h"','#include "global_define.h"\n#include "domain_service.h"')
needle='const bool is_tagged_request = isStableNpuRequestIdDescriptor(__write_cmd.m_desc);'
assert s.count(needle)==1
s=s.replace(needle,'if(swe_domain::enabled() && swe_domain::kind(swe_domain::id(__write_cmd.m_src),swe_domain::id(__write_cmd.m_dst))!=swe_domain::horizontal){auto end=swe_domain::complete(__write_cmd,__read_cmd);return CmdDelayPair(end,end);}\n        '+needle);p.write_text(s)
p=S/'includes/net_bench.h';s=p.read_text().replace('#include "global_define.h"','#include "global_define.h"\n#include "domain_service.h"')
needle='for(auto &it : *this){';assert s.count(needle)==1
s=s.replace(needle,'std::ofstream transport_of("transport_bench.txt");\n        '+needle+'\n            transport_of << it.second << std::endl;\n            if(swe_domain::enabled() && swe_domain::kind(swe_domain::id(it.second.m_src),swe_domain::id(it.second.m_dst))!=swe_domain::horizontal) continue;');p.write_text(s)
s=(OLD/'entry_guarded/interchiplet.cpp').read_text()
s=s.replace('SyncStruct* g_sync_structure = new SyncStruct();','SyncStruct* g_sync_structure = new SyncStruct();\n    setenv("SWE_RUN_ROUND", std::to_string(__round).c_str(), 1);\n    swe_domain::reset();',1)
s=s.replace('if (cmd.m_type == InterChiplet::SC_WRITE) {','if (cmd.m_type == InterChiplet::SC_WRITE && (!swe_domain::enabled() || swe_domain::kind(swe_domain::id(cmd.m_src),swe_domain::id(cmd.m_dst))==swe_domain::horizontal)) {')
(R/'interchiplet.cpp').write_text(s)
cm=(OLD/'entry_guarded/CMakeLists.txt').read_text().replace('${CMAKE_CURRENT_SOURCE_DIR}/../source/interchiplet','${CMAKE_CURRENT_SOURCE_DIR}/source/interchiplet').replace(str(OLD/'entry_guarded/interchiplet.cpp'),str(R/'interchiplet.cpp'))
(R/'CMakeLists.txt').write_text(cm)
for cmd in [['cmake','-S',str(R),'-B',str(R/'build'),'-DCMAKE_BUILD_TYPE=Release'],['cmake','--build',str(R/'build'),'-j','4']]:
 with (R/'BUILD.log').open('a') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
(R/'CONTROLLER_BUILD.json').write_text(json.dumps(dict(state='BUILT_NOT_EXECUTED',sha256=hashlib.sha256((R/'build/interchiplet').read_bytes()).hexdigest(),scope='separate HB RPC occupancy, host DRAM proxy and PCIe; standard horizontal PopNet feedback; unknown HB fixed latency excluded'),indent=2))
print('domain controller built')

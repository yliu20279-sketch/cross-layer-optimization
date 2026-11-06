import json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent;OLD=B/'swe_qwen3_legosim_integration_20261030_v1';A=OLD/'unified_layers_fifo_v2'
s=(A/'bridge_pic.cpp').read_text().replace('#include <memory>','#include <memory>\n#include <cstdlib>')
s=s.replace('static int output_fd=-1;','static int output_fd=-1,input_fd=-1;\nstatic int rank=std::atoi(std::getenv("SWE_RANK"));')
s=s.replace('c.dram_chiplet_x=2;c.dram_chiplet_y=0;', 'c.dram_chiplet_x=rank%4;c.dram_chiplet_y=8+rank/4;')
s=s.replace('c.dram_chiplet_grid_cols=3;', 'c.dram_chiplet_grid_cols=4;').replace('o.self_x=1;o.self_y=0;', 'o.self_x=rank%4;o.self_y=rank/4;')
s=s.replace('if(!wr)close(fd);','')
lines=s.splitlines()
for i,line in enumerate(lines):
 if ' int um_recv(' in line:
  lines[i]='extern "C" __attribute__((visibility("default"))) int um_recv(void*p,unsigned long long n){TRY auto s=InterChiplet::receiveSync(0,4,rank%4,rank/4);if(input_fd<0)input_fd=open(s.c_str(),O_RDONLY);io(input_fd,(char*)p,n,false);auto t=InterChiplet::readSync(rt->chipCycle(),0,4,rank%4,rank/4,n,0);rt->chipCycle()=std::max(rt->chipCycle(),(unsigned long long)t);return 0;END}'
 if ' int um_send(' in line:
  lines[i]='extern "C" __attribute__((visibility("default"))) int um_send(const void*p,unsigned long long n){TRY auto s=InterChiplet::sendSync(rank%4,rank/4,0,4);if(output_fd<0)output_fd=open(s.c_str(),O_WRONLY);io(output_fd,(char*)p,n,true);auto t=InterChiplet::writeSync(rt->chipCycle(),rank%4,rank/4,0,4,n,0);rt->chipCycle()=std::max(rt->chipCycle(),(unsigned long long)t);return 0;END}'
(R/'bridge_actor.cpp').write_text('\n'.join(lines)+'\n')
cmd=json.loads((A/'BUILD_COMMAND.json').read_text());cmd=[v.replace(str(A/'bridge_pic.cpp'),str(R/'bridge_actor.cpp')).replace(str(A/'libunified.so'),str(R/'libactor.so')) for v in cmd]
W=Path('/mnt/sdb1/h3240101068/npusim_ramulator2_validation_20260826/workspace');I=W/'interchiplet/includes';S=Path('/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/snipersim')
commands=[cmd,['g++','-O2','-std=c++17','-I'+str(I),str(R/'gateway.cpp'),'-o',str(R/'gateway')],['g++','-O2','-std=c++17','-I'+str(I),'-I'+str(S/'include'),str(R/'host.cpp'),str(W/'interchiplet_host/lib/libinterchiplet_c.a'),'-pthread','-o',str(R/'host')]]
(R/'ACTOR_BUILD_COMMANDS.json').write_text(json.dumps(commands,indent=2))
for cmd in commands:
 with (R/'ACTOR_BUILD.log').open('a') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
print('actors built')

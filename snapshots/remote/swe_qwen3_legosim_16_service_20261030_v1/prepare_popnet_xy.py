import shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;OLD=R.parent/'swe_qwen3_legosim_integration_20261030_v1';S=R/'popnet_xy_source'
shutil.copytree(OLD/'popnet_quiet_source',S)
p=S/'sim_router.cc';s=p.read_text().replace('#include <math.h>','#include <math.h>\n#include <cstdlib>\n#include <stdexcept>\n#include <fstream>')
needle='\tportMap=make_unique<vector<SLinkInfo>[]>(vertexCnt);';assert s.count(needle)==1
patch='''
 if(std::getenv("SWE_CANONICAL_XY")){
  if(vertexCnt!=17)throw std::runtime_error("canonical XY requires16 NPU plus gateway");
  std::ofstream audit("routing_xy.csv");audit<<"source,destination,next_hop\\n";
  for(long src=0;src<17;src++)for(long dst=0;dst<17;dst++){
   long next=src;
   if(src!=dst){
    if(src==16)next=0;
    else if(dst==16&&src==0)next=16;
    else {long target=dst==16?0:dst;long x=src%4,tx=target%4,y=src/4,ty=target/4;
     next=x!=tx?src+(tx>x?1:-1):src+(ty>y?4:-4);}
   }
   routingTable[src][dst]=next;audit<<src<<','<<dst<<','<<next<<'\\n';
  }
 }
'''
s=s.replace(needle,patch+needle)
needle='void CGraphTopo::init()';pos=s.index(needle);pre=s[:pos];idx=pre.rfind('\n}')
pre=pre[:idx]+'''\n if(std::getenv("SWE_CANONICAL_XY"))for(long s=0;s<17;s++)for(long d=0;d<17;d++)if(s!=d && !nextHop_port_map[s].count(routingTable[s][d]))throw std::runtime_error("XY next hop not an actual graph edge");\n'''+pre[idx:]
p.write_text(pre+s[pos:])
for cmd in [['cmake','-S',str(S),'-B',str(R/'popnet_xy_build')],['cmake','--build',str(R/'popnet_xy_build'),'-j','4']]:
 with (R/'POPNET_XY_BUILD.log').open('a') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
print('canonical XY PopNet built')

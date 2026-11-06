"""Generate a new backend variant; old sources/binaries are never changed.

This variant couples page translation and project injection controls to actual
Ramulator/PopNet calls. Compute remains analytical, not target numeric GEMM.
"""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'runtime/native_main_fp16_hook.cc').read_text(encoding='utf-8')
source=source.replace('#include "p0_event_sink.h"','#include "p0_event_sink.h"\n#include "live_controls.h"')
source=source.replace('uint64_t packets=0;','uint64_t packets=0,remaining_flits=0;')
begin=source.index('bool mapped=envs("HB_IDENTITY")')
end=source.index(' p0::EventSink',begin)
source=source[:begin]+'''p0live::AddressMap page_map(std::vector<uint64_t>(16,512ull*1024*1024));
 std::map<p0live::Page,bool> movable_pages;
 {std::ifstream input(envs("P0_OBJECTS"));uint64_t count;input>>count;require(bool(input)&&count>0,"objects absent");
  for(uint64_t i=0;i<count;++i){uint64_t id,address,bytes,generation;int rank,movable;input>>id>>rank>>address>>bytes>>generation>>movable;
   require(bool(input)&&bytes>0&&address<=UINT64_MAX-bytes,"bad object metadata");
   for(uint64_t p=address/4096;p<=(address+bytes-1)/4096;++p)
    require(movable_pages.emplace(p0live::Page{rank,p},bool(movable)).second,"objects share frame");}}
 std::map<p0live::Page,uint64_t> candidate;
 {std::ifstream f(dir+"/rr_map.txt");int p;uint64_t a,b;while(f>>p>>a>>b){
  require(movable_pages.count({p,a}),"RR page outside object inventory");
  page_map.add(p,a,b,movable_pages.at({p,a}));candidate[{p,a}]=b;}
  require(candidate.size()==movable_pages.size(),"RR object page coverage differs");}
 {std::ifstream f(envs("P0_CA_MAP"));int p;uint64_t a,b;std::map<p0live::Page,uint64_t> installed;
  while(f>>p>>a>>b)require(installed.emplace(p0live::Page{p,a},b).second,"duplicate CA page");
  page_map.install(installed,0);}
 auto address=[&](int rank,uint64_t a,uint64_t n){return page_map.translate(rank,a,n,page_map.generation());};
 std::string control=envs("P0_LINK_CONTROL");require(control=="off"||control=="project_dynamic","unknown project link control");
 bool link_enabled=control=="project_dynamic";
 uint64_t link_interval=std::stoull(envs("P0_LINK_INTERVAL_NS"));
 uint64_t link_switch=std::stoull(envs("P0_LINK_SWITCH_NS"));
 p0live::LinkController link(link_interval,link_switch);
 std::map<size_t,uint64_t> link_tokens;uint64_t nextmapid=0;
''' +source[end:]
source=source.replace('if(!r.packets)finish(i,t);',
    'if(link_enabled){link.callback(link_tokens.at(id),t);link_tokens.erase(id);}'
    'if(!r.packets&&!r.remaining_flits)finish(i,t);')
begin=source.index(' auto transfer=')
end=source.index(' while(done<rs.size())',begin)
source=source[:begin]+''' auto transfer=[&](size_t i){auto&r=rs[i];if(r.kind!=2){finish(i,now);return;}
  require(r.src!=r.dst&&r.bytes>0,"invalid NET");
  r.remaining_flits=uint64_t(std::ceil(double(r.bytes)/(config.flit_size()*8.)));r.state=2;};
 auto local_scope=[](int a,int b){return std::abs(a%4-b%4)+std::abs(a/4-b/4)==1;};
 auto inject=[&](){uint64_t local=0,global=0;
  for(auto&r:rs)if(r.state==2&&r.remaining_flits)(local_scope(r.src,r.dst)?local:global)+=r.remaining_flits;
  if(link_enabled&&(local||global))link.select(local,global,now);
  for(size_t i=0;i<rs.size();++i){auto&r=rs[i];if(r.state!=2)continue;
   while(r.remaining_flits){uint64_t flitbytes=config.flit_size()*8;
    require(flitbytes>0&&(!link_enabled||flitbytes<=512),"unsupported flit occupancy");
    int chunk=std::min(r.remaining_flits,link_enabled?std::min(uint64_t(32),512/flitbytes):uint64_t(32));
    uint64_t occupancy=uint64_t(chunk)*flitbytes;bool local=local_scope(r.src,r.dst);
    if(link_enabled&&!link.can_issue(local,occupancy,now))break;
    auto pid=nextpacket++;if(link_enabled)link_tokens[pid]=link.accept(local,occupancy,now);
    packets[pid]=i;++r.packets;r.remaining_flits-=chunk;
    add_type s={r.src%4,r.src/4},d={r.dst%4,r.dst/4};SPacket p;p.startTime=now;
    p.sourceAddress=s;p.destinationAddress=d;p.packetSize=chunk;p.id=pid;
    if(offline)fake_net.push_back({now+2,pid});else{network.router(s).inputTrace(p);network.router(s).receive_packet();}
    trace<<"NOC_ISSUE,"<<now<<','<<r.id<<','<<pid<<','<<r.rank<<",0,"<<chunk<<",0\\n";
   }
  }
 };
''' +source[end:]
anchor='  for(size_t i=0;i<rs.size();++i){auto&r=rs[i];if(r.state==3'
assert source.count(anchor)==1
source=source.replace(anchor,'  inject();\n'+anchor,1)
source=source.replace('auto rank=r.rank;auto token=t.token;',
                      'auto rank=r.rank;auto map_id=nextmapid;auto map_generation=page_map.generation();auto token=t.token;')
source=source.replace('object=t.object](Ramulator::Request&)',
                      'object=t.object,map_id,map_generation](Ramulator::Request&)')
source=source.replace('auto&q=rs[i];p0sink.callback',
                      'auto&q=rs[i];page_map.callback(map_id,map_generation);p0sink.callback')
source=source.replace('op.accept(t);p0sink.accept',
                      'page_map.accept(map_id,rank,t.address,bytes,map_generation);++nextmapid;op.accept(t);p0sink.accept')
source=source.replace('p0sink.finish();require(issued==callbacks&&packets.empty(),',
                      'p0sink.finish();require(page_map.inflight()==0&&link.inflight()==0&&link_tokens.empty(),"live controls not drained");require(issued==callbacks&&packets.empty(),')
source=source.replace('std::ofstream result(out+"/summary.json");',
    'std::ofstream control_out(out+"/live_controls.json");control_out<<"{\\"map_generation\\":"<<page_map.generation()<<",\\"mapped_transactions\\":"<<nextmapid<<",\\"link_switches\\":"<<link.switches<<",\\"injection_bytes\\":"<<link.accepted_bytes<<",\\"target_numerical_compute\\":false,\\"author_HiBand_equivalent\\":false}\\n";std::ofstream result(out+"/summary.json");')
target=ROOT/'runtime/native_live_controls.cc'
target.write_bytes(source.encode('utf-8'))
receipt={'source':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
         'scope':'actual page translation and project injection gating; analytical compute unchanged',
         'author_hiband_equivalent':False,'sem_moe_execution_complete':False,'formal_performance_runs':0}
(ROOT/'evidence/LIVE_SOURCE.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps(receipt))

#include <ramulator/base/config.h>
#include <ramulator/base/factory.h>
#include <ramulator/base/request.h>
#include <ramulator/frontend/i_frontend.h>
#include <ramulator/memory_system/i_memory_system.h>
#include "configuration.h"
#include "sim_foundation.h"
#include "mess_queue.h"
#include "SRGen.h"
#include "tiled_phase.h"
#include "phase_engine.h"
#include "p0_event_sink.h"
#include "live_controls.h"
#include <array>
#include <fstream>
#include <sstream>
#include <memory>
#include <functional>
#include <cmath>
#include <set>

#include <map>

#include <iostream>
#include <iomanip>
static std::function<void(size_t,double)>packet_callback;
void coupled_packet_complete(size_t id,double t){if(!packet_callback)throw std::runtime_error("packet callback absent");packet_callback(id,t);}
std::string envs(const char*k){auto v=std::getenv(k);if(!v)throw std::runtime_error(k);return v;}
using tiledfp16::require;
struct Region{int id,rank,request,kind,linear,src,dst;uint64_t M,K,N,A,B,C,ao,bo,co,credit,service,bytes;std::vector<int>parents;std::vector<realv2::Segment>segments;int state=0;double ready=0,done=-1,compute_finish=0;bool computing=false,read_reported=false;uint64_t packets=0,remaining_flits=0;std::unique_ptr<tiledfp16::Operation>tile;std::unique_ptr<realv2::Operation>plain;};
int main(int argc,char**argv){try{
 bool offline=std::getenv("HB_OFFLINE")&&std::string(std::getenv("HB_OFFLINE"))=="1";auto dir=envs("HB_GRAPH"),out=envs("HB_OUT");p0live::AddressMap page_map(std::vector<uint64_t>(16,512ull*1024*1024));
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
 p0::EventSink p0sink(out+"/ca_weight_events.jsonl",envs("P0_OBJECTS"),envs("P0_REQUESTS"),envs("P0_MODEL_DTYPE"),envs("P0_TRACE_CLASS"));
 SRGen rng;configuration config(argc,argv);mess_queue network_queue(0);sim_foundation network;
 std::array<Ramulator::IFrontEnd*,16>fronts;std::array<Ramulator::IMemorySystem*,16>memories;double tck=0;
 for(int p=0;p<16;++p){auto cfg=Ramulator::Config::parse_config_file(envs("HB_RAM_CONFIG"));fronts[p]=Ramulator::Factory::create_frontend(cfg);memories[p]=Ramulator::Factory::create_memory_system(cfg);fronts[p]->connect_memory_system(memories[p]);memories[p]->connect_frontend(fronts[p]);require(memories[p]->get_tx_bytes()==256,"native tx mismatch");tck=memories[p]->get_tCK();}require(std::abs(tck-1.25)<1e-9,"DRAM clock mismatch");
 std::vector<Region>rs;std::ifstream f(dir+"/regions.txt");int count;f>>count;require(count>0,"emptyregions");
 for(int i=0;i<count;++i){Region r;int np,ns;f>>r.id>>r.rank>>r.request>>r.kind>>r.linear>>r.src>>r.dst>>r.M>>r.K>>r.N>>r.A>>r.B>>r.C>>r.ao>>r.bo>>r.co>>r.credit>>r.service>>r.bytes>>np;for(int j=0;j<np;++j){int p;f>>p;r.parents.push_back(p);}f>>ns;for(int j=0;j<ns;++j){realv2::Segment s;int w;f>>s.address>>s.bytes>>s.object>>w;s.write=w;r.segments.push_back(s);}require(bool(f),"bad region record");rs.push_back(std::move(r));}
 std::map<int,size_t>indices;for(size_t i=0;i<rs.size();++i)require(indices.emplace(rs[i].id,i).second,"duplicate region");
 std::array<std::unique_ptr<tiledfp16::Sram>,16>pools;std::ifstream sf(dir+"/sram.txt");for(int i=0;i<16;++i){uint64_t cap;sf>>cap;require(cap>0&&cap<=4194304,"badpool");pools[i]=std::make_unique<tiledfp16::Sram>(cap);}
 std::map<int,uint64_t>tilecost;std::ifstream tf(dir+"/timing.txt");int n;uint64_t cyc;while(tf>>n>>cyc)tilecost[n]=cyc;
 std::array<int,16>compute_owner;compute_owner.fill(-1);std::map<size_t,size_t>packets;uint64_t nextpacket=0,issued=0,callbacks=0,readbytes=0,writebytes=0,tiles=0,done=0;double now=0,nextdram=tck,lastprogress=0;std::ofstream trace(offline?"/dev/null":out+"/events.csv"),nodes(out+"/nodes.csv");trace<<std::setprecision(17);nodes<<std::setprecision(17);trace<<"event,time,region,token,rank,address,bytes,write\n";nodes<<"original_id,event,time,region\n";
 std::vector<std::function<void(Ramulator::Request&)>> fake;std::vector<std::pair<double,size_t>> fake_net;auto receive=[&](int rank,int typ,uint64_t addr,int owner,int ingress,std::function<void(Ramulator::Request&)> cb,int bytes){if(offline){if(fake.size()>=32)return false;fake.push_back(cb);return true;}return fronts[rank]->receive_external_requests(typ,addr,owner,ingress,cb,bytes);};

 auto finish=[&](size_t i,double t){auto&r=rs[i];require(r.state!=3&&r.packets==0,"duplicate/early region completion");if(r.tile)require(r.tile->consumer_ready()&&r.tile->outstanding()==0,"tile unfinished");if(r.plain)require(r.plain->consumer_ready()&&r.plain->outstanding()==0,"plain unfinished");r.state=3;r.done=t;++done;lastprogress=now;if(r.linear>=0)nodes<<r.linear<<",done,"<<t<<','<<r.id<<'\n';else nodes<<r.id<<",done,"<<t<<','<<r.id<<'\n';};
 packet_callback=[&](size_t id,double t){auto it=packets.find(id);require(it!=packets.end(),"unknown/double NoC callback");auto i=it->second;packets.erase(it);auto&r=rs[i];require(r.packets>0,"packet underflow");--r.packets;trace<<"NOC_DONE,"<<t<<','<<r.id<<','<<id<<','<<r.rank<<",0,0,0\n";if(link_enabled){link.callback(link_tokens.at(id),t);link_tokens.erase(id);}if(!r.packets&&!r.remaining_flits)finish(i,t);};
 auto transfer=[&](size_t i){auto&r=rs[i];if(r.kind!=2){finish(i,now);return;}
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
    trace<<"NOC_ISSUE,"<<now<<','<<r.id<<','<<pid<<','<<r.rank<<",0,"<<chunk<<",0\n";
   }
  }
 };
 while(done<rs.size()){
  require(now<1000000000.&&now-lastprogress<100000000.,"native watchdog");if(offline){Ramulator::Request dummy;nextdram=now;auto callbacks=fake;fake.clear();for(auto i=callbacks.rbegin();i!=callbacks.rend();++i)(*i)(dummy);for(auto it=fake_net.begin();it!=fake_net.end();){if(it->first<=now){packet_callback(it->second,it->first);it=fake_net.erase(it);}else ++it;}}else network_queue.coupled_advance(now);while(!offline&&nextdram<=now+1e-8){for(int p=0;p<16;++p)memories[p]->tick();nextdram+=tck;}
  inject();
  for(size_t i=0;i<rs.size();++i){auto&r=rs[i];if(r.state==3||r.state==2)continue;
   if(r.state==0){bool ready=true;for(int p:r.parents){auto&q=rs[indices.at(p)];ready&=q.state==3;if(q.state==3)r.ready=std::max(r.ready,q.done);}if(!ready)continue;
    if(r.kind==1){r.tile=std::make_unique<tiledfp16::Operation>(*pools[r.rank],r.credit,16,r.M,r.K,r.N,r.A,r.B,r.C,r.ao,r.bo,r.co);require(r.tile->try_start(),"conservative SRAM witness violated");nodes<<r.id<<",read_start,"<<now<<','<<r.id<<'\n';}
    else{r.plain=std::make_unique<realv2::Operation>(r.credit,16,r.segments,r.service);r.plain->release();nodes<<r.id<<",start,"<<now<<','<<r.id<<'\n';}r.state=1;
   }
   if(r.tile){auto&op=*r.tile;
    if(op.phase==tiledfp16::Phase::Ready)require(op.try_start(),"SRAM reentry blocked despite conservative witness");
    if(op.phase==tiledfp16::Phase::Compute&&r.computing&&now>=r.compute_finish){
     try{op.compute_complete(now);r.computing=false;compute_owner[r.rank]=-1;++tiles;}catch(const std::runtime_error&e){if(std::string(e.what())!="early compute completion")throw;}
    }
    if(op.phase==tiledfp16::Phase::ComputeReady&&compute_owner[r.rank]<0){auto k=op.k_offset(),nt=op.n_offset();uint64_t nn=std::min(uint64_t(64),r.N-nt);uint64_t service=tilecost.at(nn);if(k>0)service+=(nn+15)/16+3;if(k+64>=r.K){service+=(nn+15)/16;if(r.kind==1&&r.service)service+=r.service;}op.admit_compute(now,service);r.compute_finish=now+service;compute_owner[r.rank]=r.id;r.computing=true;}
    while(op.pending()){auto t=op.peek();auto a=address(r.rank,t.address,t.bytes);auto rank=r.rank;auto map_id=nextmapid;auto map_generation=page_map.generation();auto token=t.token;auto bytes=t.bytes;auto wr=t.write;bool ok=receive(rank,wr?Ramulator::Request::Type::Write:Ramulator::Request::Type::Read,a,r.request,r.credit,[&,i,rank,token,a,bytes,wr,object=t.object,map_id,map_generation](Ramulator::Request&){auto&q=rs[i];page_map.callback(map_id,map_generation);p0sink.callback(rank,object,q.credit,token,wr,nextdram);q.tile->callback(q.credit,token);if(!q.read_reported&&q.tile->phase==tiledfp16::Phase::ComputeReady&&q.tile->k_offset()+64>=q.K&&q.tile->n_offset()+64>=q.N){nodes<<q.id<<",read_done,"<<nextdram<<','<<q.id<<'\n';q.read_reported=true;}++callbacks;trace<<"DRAM_DONE,"<<nextdram<<','<<q.id<<','<<token<<','<<rank<<','<<a<<','<<bytes<<','<<wr<<'\n';lastprogress=now;},int(bytes));if(!ok)break;page_map.accept(map_id,rank,t.address,bytes,map_generation);++nextmapid;op.accept(t);p0sink.accept(r.request,rank,t.object,r.credit,token,t.address,bytes,wr,now);++issued;(wr?writebytes:readbytes)+=bytes;trace<<"DRAM_ISSUE,"<<now<<','<<r.id<<','<<token<<','<<rank<<','<<a<<','<<bytes<<','<<wr<<'\n';}
    // Last read gate is reached before final K compute, not region start.
    if(!r.read_reported&&op.k_offset()+64>=r.K&&op.n_offset()+64>=r.N&&op.phase!=tiledfp16::Phase::Read){nodes<<r.id<<",read_done,"<<now<<','<<r.id<<'\n';r.read_reported=true;}
    if(op.consumer_ready())transfer(i);
   }else{auto&op=*r.plain;
    if(op.phase==realv2::Phase::Compute&&r.computing&&now>=r.compute_finish){try{op.compute_complete(now);r.computing=false;compute_owner[r.rank]=-1;}catch(const std::runtime_error&e){if(std::string(e.what())!="early or duplicate compute completion")throw;}}
    if(op.phase==realv2::Phase::ComputeReady&&(r.service==0||compute_owner[r.rank]<0)){op.admit_compute(now);if(!r.service)op.compute_complete(now);else{r.compute_finish=now+r.service;compute_owner[r.rank]=r.id;r.computing=true;}}
    while(op.pending()){auto t=op.peek();auto a=address(r.rank,t.address,t.bytes);auto rank=r.rank;auto map_id=nextmapid;auto map_generation=page_map.generation();auto token=t.token;auto bytes=t.bytes;auto wr=t.write;bool ok=receive(rank,wr?Ramulator::Request::Type::Write:Ramulator::Request::Type::Read,a,r.request,r.credit,[&,i,rank,token,a,bytes,wr,object=t.object,map_id,map_generation](Ramulator::Request&){auto&q=rs[i];page_map.callback(map_id,map_generation);p0sink.callback(rank,object,q.credit,token,wr,nextdram);q.plain->callback(q.credit,token);++callbacks;trace<<"DRAM_DONE,"<<nextdram<<','<<q.id<<','<<token<<','<<rank<<','<<a<<','<<bytes<<','<<wr<<'\n';lastprogress=now;},int(bytes));if(!ok)break;page_map.accept(map_id,rank,t.address,bytes,map_generation);++nextmapid;op.accept(t);p0sink.accept(r.request,rank,t.object,r.credit,token,t.address,bytes,wr,now);++issued;(wr?writebytes:readbytes)+=bytes;trace<<"DRAM_ISSUE,"<<now<<','<<r.id<<','<<token<<','<<rank<<','<<a<<','<<bytes<<','<<wr<<'\n';}
    if(op.consumer_ready())transfer(i);
   }
  }
  if(!offline&&(!packets.empty()||network_queue.message_queue_size()))for(auto&r:network.inter_network())r.router_sim_pwr(1.0);now+=1;
 }
 p0sink.finish();require(page_map.inflight()==0&&link.inflight()==0&&link_tokens.empty(),"live controls not drained");require(issued==callbacks&&packets.empty(),"backend not drained");for(auto&p:pools)require(p->used()==0,"SRAM leak");for(auto&r:rs)for(int p:r.parents)require(r.done>=rs[indices.at(p)].done,"causal violation");std::ofstream control_out(out+"/live_controls.json");control_out<<"{\"map_generation\":"<<page_map.generation()<<",\"mapped_transactions\":"<<nextmapid<<",\"link_switches\":"<<link.switches<<",\"injection_bytes\":"<<link.accepted_bytes<<",\"target_numerical_compute\":false,\"author_HiBand_equivalent\":false}\n";std::ofstream result(out+"/summary.json");result<<"{\"status\":\""<<(offline?"PASS_CALLBACK_MOCK":"PASS_NATIVE_JOINT_IDENTITY_CANDIDATE")<<"\",\"offline_mock\":"<<(offline?"true":"false")<<",\"cycles\":"<<std::setprecision(17)<<now-1<<",\"regions\":"<<rs.size()<<",\"transactions\":"<<issued<<",\"callbacks\":"<<callbacks<<",\"read_bytes\":"<<readbytes<<",\"write_bytes\":"<<writebytes<<",\"tiles\":"<<tiles<<",\"packets\":"<<nextpacket<<",\"backend\":\"full_transaction_Ramulator2_fullpayload_PopNet_analytical_compute\"}\n";return 0;
}catch(std::exception&e){std::cerr<<"FAILED "<<e.what()<<"\n";return 1;}}

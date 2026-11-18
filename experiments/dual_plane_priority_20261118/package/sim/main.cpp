#include "Vdut.h"
#include "verilated.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <deque>
#include <fstream>
#include <functional>
#include <iostream>
#include <map>
#include <memory>
#include <numeric>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>
using namespace std;
using Word=array<uint32_t,8>;
static void need(bool x,const string&s){if(!x)throw runtime_error(s);}
static uint32_t bits(const uint32_t*p,int lo,int n){uint64_t v=p[lo/32];if(lo%32+n>32)v|=uint64_t(p[lo/32+1])<<32;return uint32_t(v>>(lo%32))&(n==32?~0u:(1u<<n)-1);}
static Word pattern(uint32_t id,int beat){Word w{};for(int i=0;i<8;i++)w[i]=uint32_t(id*2654435761u)^uint32_t((beat+1)*2246822519u)^uint32_t(i*3266489917u);return w;}
struct Packet{
 uint32_t id,txn=0;int src,dst,op,bytes,vn,client;uint64_t address=0;
 int at=0,off=-1,readybeats=0,sent=-1,received=-1,committed=-1,inject=-1;
 bool circuit=false,hold=false,arrived=false,from_bank=false,saved_route=false,old_circuit=false;int cs=0,version=0,old_cs=0,old_version=0;
 vector<Word> body,got,tx_data,bank_data;uint32_t source_address=0,destination_address=0;int receive_slot=-1;
};
struct Job{uint32_t id;int kind,at,beat=0;}; // source read, receive write, bank read
struct Path{int src,dst;vector<int> cs;};
static int peer(int c,int p){
 if(c<9&&p<4)return 4*(c/3)+c%3+(p>=2?4:0)+p%2;
 static const map<int,int> m={{4,63},{14,68},{34,73},{44,78},{45,66},{46,72},{47,20},{50,61},{51,77},{52,30},{55,76},{56,62},{57,50},{60,71},{61,67},{62,60}};
 auto i=m.find(c*5+p);return i==m.end()?-1:i->second;
}
static vector<Path> paths(int src,int dst){
 vector<Path> result;
 function<void(int,vector<int>,int)> dfs=[&](int c,vector<int> p,int mask){
  p.push_back(c);mask|=1<<c;
  for(int a=0;a<4;a++)if(peer(c,a)==dst)result.push_back({src,dst,p});
  for(int a=0;a<5;a++){int x=peer(c,a);if(x>=16&&!(mask&(1<<((x-16)/5))))dfs((x-16)/5,p,mask);}
 };
 for(int c=0;c<9;c++)for(int a=0;a<4;a++)if(peer(c,a)==src)dfs(c,{},0);
 sort(result.begin(),result.end(),[](auto&a,auto&b){return make_pair(a.cs.size(),a.cs)<make_pair(b.cs.size(),b.cs);});
 return result;
}
static array<int,13> image(const vector<Path>&ps){
 array<int,13> out{};set<int> used;
 for(auto&p:ps)for(size_t k=0;k<p.cs.size();k++){
  int c=p.cs[k],a=-1,b=-1;
  need(used.insert(c).second,"CS overlap in plan");
  for(int port=0;port<5;port++){
   int q=peer(c,port);
   if(k==0?q==p.src:q>=16&&(q-16)/5==p.cs[k-1])a=port;
   if(k+1==p.cs.size()?q==p.dst:q>=16&&(q-16)/5==p.cs[k+1])b=port;
  }
  need(a>=0&&b>=0&&a!=b,"unwired plan");
  out[c]=32+(b<<2)+(a-(a>b));
 }
 return out;
}
struct Harness{
 unique_ptr<Vdut> d=make_unique<Vdut>();
 int now=0,nextid=1,done=0,backpressure=0,block_node=-1,block_until=0;bool expectedDual=true,runTraffic=true;
 int region=0;uint32_t command=0x80000000u;int lastack=-1,lastok=-1;uint32_t lastackid=0;unsigned expected_errors=0;
 map<uint32_t,Packet> packets;
 array<int,13> active_image{};vector<Path> active_paths;
 array<array<deque<uint32_t>,3>,16> source;
 array<array<deque<Job>,3>,16> jobs;
 array<array<int,3>,16> rxslots{},assembly{},beat{},sramfirst{};
 array<int,16> sramptr{},outstanding{},bank_reserved{};
 array<vector<uint32_t>,16> memory;array<uint32_t,16> source_cursor{},destination_cursor{};
 array<array<array<bool,16>,3>,16> receive_used{};
 vector<tuple<int,int,int,uint32_t>> callback;
 uint64_t payload_hash=1469598103934665603ull,source_services=0,bank_services=0,dest_services=0;
 int bankLatency=8;long long clock_ns=1;bool hostAccepted=false;
 Harness(bool dual=true):expectedDual(dual){
  for(auto&a:assembly)a.fill(-1);
  for(int n=0;n<16;n++){
   memory[n].resize(4*1024*1024/4);source_cursor[n]=65536;destination_cursor[n]=2*1024*1024;
   for(int a=0;a<1024;a++)for(int k=0;k<16;k++)memory[n][a*16+k]=uint32_t(n*1664525u)^uint32_t(a*1013904223u)^uint32_t(k*374761393u);
  }
  d->clk=0;d->reset=1;d->host_valid=0;d->ack_ready=1;d->hiband_mode=0;d->seq_start=0;d->seq_version=0;d->retire_valid=0;for(int k=0;k<3;k++)d->seq_plan[k]=0;
  for(int n=0;n<16;n++){d->client_valid[n]=0;d->client_first[n]=0;d->client_circuit[n]=0;d->rx_ready[n]=7;}
  for(int i=0;i<4;i++){d->eval();d->clk=1;d->eval();d->clk=0;d->eval();}
  d->reset=0;
 }
 Packet& add(int s,int t,int op,int bytes,int at=0,bool cs=false,int attachment=0,int version=0){
  uint32_t id=nextid++;
  Packet p;p.id=id;p.src=s;p.dst=t;p.op=op;p.bytes=bytes;p.at=at;p.vn=op==1?1:op==2?2:0;p.client=p.vn;
  p.circuit=cs;p.cs=attachment;p.version=version;
  for(int b=0;b<(bytes+31)/32;b++)p.body.push_back(pattern(id,b));
  p.tx_data=p.body;
  if(op==3||op==4){
   p.source_address=source_cursor[s];source_cursor[s]+=uint32_t(p.body.size()*32);need(source_cursor[s]<=2*1024*1024,"source SRAM allocation exceeded");
   for(size_t b=0;b<p.body.size();b++)for(int k=0;k<8;k++)memory[s][p.source_address/4+b*8+k]=p.body[b][k];
   if(op==3){p.destination_address=destination_cursor[t];destination_cursor[t]+=uint32_t(p.body.size()*32);need(destination_cursor[t]<=0x3f0000,"destination SRAM allocation exceeded");}
  }
  packets.emplace(id,p);source[s][p.client].push_back(id);return packets.at(id);
 }
 void gets(int s,int t,int at){
  auto&p=add(s,t,1,0,at);p.txn=p.id;p.address=uint64_t(p.id%1024)*64;p.bank_data.resize(2);
  Packet reply;reply.id=p.id|0x40000000u;reply.txn=p.id;reply.src=t;reply.dst=s;reply.op=2;reply.vn=2;reply.client=2;reply.bytes=64;reply.at=0x7fffffff;reply.from_bank=true;
  for(int b=0;b<2;b++){Word w{};for(int k=0;k<8;k++)w[k]=memory[t][p.address/4+b*8+k];reply.body.push_back(w);}
  packets.emplace(reply.id,reply);
 }
 void callbacks(){
  vector<tuple<int,int,int,uint32_t>> later;
  for(auto [when,kind,b,id]:callback){
   if(when>now){later.push_back({when,kind,b,id});continue;}
   auto&p=packets.at(id);
   if(kind==0)++p.readybeats;
   else if(kind==1){
    for(size_t b=0;b<p.body.size();b++)for(int k=0;k<8;k++)need(memory[p.dst][p.destination_address/4+b*8+k]==p.body[b][k],"destination SRAM write mismatch");
    p.committed=now;++done;--rxslots[p.dst][p.vn];
    receive_used[p.dst][p.vn][p.receive_slot]=false;
    if(p.op==2){--outstanding[p.dst];d->retire_valid|=1<<p.dst;d->retire_txn[p.dst]=p.txn;}
   }else{
    auto&r=packets.at(id|0x40000000u);r.at=now;r.tx_data=p.bank_data;
    source[r.src][2].push_back(r.id);r.readybeats=2;
    p.committed=now;++done;--rxslots[p.dst][p.vn];receive_used[p.dst][p.vn][p.receive_slot]=false;
   }
  }
  callback.swap(later);
 }
 void memory_tick(){
  for(int n=0;n<16;n++)for(int t=0;t<3;t++){
   int v=(sramptr[n]+t)%3;auto&q=jobs[n][v];if(q.empty()||q.front().at>now)continue;
   auto&j=q.front();auto&p=packets.at(j.id);
   ++j.beat;
   if(j.kind==0){
    ++source_services;for(int k=0;k<8;k++)p.tx_data[j.beat-1][k]=memory[n][p.source_address/4+(j.beat-1)*8+k];
    callback.push_back({now+1,0,j.beat-1,j.id});
   }
   else if(j.kind==1){
    ++dest_services;auto&w=p.got.at(j.beat-1);
    for(int k=0;k<8;k++){memory[n][p.destination_address/4+(j.beat-1)*8+k]=w[k];payload_hash^=w[k];payload_hash*=1099511628211ull;}
   }else{
    ++bank_services;for(int k=0;k<8;k++)p.bank_data[j.beat-1][k]=memory[n][p.address/4+(j.beat-1)*8+k];
   }
   int count=j.kind==2?2:int(p.body.size());
   if(j.beat>=count){if(j.kind!=0)callback.push_back({now+1,j.kind,0,j.id});q.pop_front();}
   sramptr[n]=(v+1)%3;break;
  }
 }
 void drive(){
  for(int n=0;n<16;n++){
   d->client_valid[n]=0;d->client_first[n]=0;d->client_circuit[n]=0;d->rx_ready[n]=0;
   for(int v=0;v<3;v++){
    bool avail=assembly[n][v]>=0||rxslots[n][v]<16;
    if(v==1&&bank_reserved[n]>=16&&assembly[n][v]<0)avail=false;
    if(backpressure&&((now+n*3+v)%backpressure)<3)avail=false;
    if(n==block_node&&now<block_until)avail=false;
    if(avail)d->rx_ready[n]|=1<<v;
    auto&q=source[n][v];if(q.empty()||!runTraffic)continue;
    if(v==0&&packets.at(q.front()).off<0&&packets.at(q.front()).hold){
     auto next=find_if(q.begin(),q.end(),[&](auto id){auto&p=packets.at(id);return !p.hold&&p.at<=now;});
     if(next!=q.end())rotate(q.begin(),next,next+1);
    }
    auto&p=packets.at(q.front());
    if(p.at>now||p.hold||(p.off<0&&p.op==1&&outstanding[n]>=16))continue;
    if(p.off>=0&&p.off>=p.readybeats)continue;
    d->client_valid[n]|=1<<v;
    d->client_first[n]|=(p.off<0?1:0)<<v;
    d->client_circuit[n]|=int(p.circuit)<<v;
    d->client_op[n][v]=p.op;d->client_dst[n][v]=p.dst;d->client_cs[n][v]=p.cs;
    d->client_id[n][v]=p.id;d->client_txn[n][v]=p.txn;
    d->client_bytes[n][v]=p.bytes;d->client_version[n][v]=p.version;
    for(int k=0;k<8;k++)d->client_data[n][v][k]=p.off<0?0:p.tx_data.at(p.off)[k];
    if(p.off<0&&p.op==1){d->client_data[n][v][0]=uint32_t(p.address);d->client_data[n][v][1]=uint32_t(p.address>>32);}
   }
  }
 }
 void receive(int n,const uint32_t*f){
  int v=bits(f,258,2);bool head=bits(f,257,1),tail=bits(f,256,1);
  need(v<3,"bad VN");
  if(head){
   uint32_t id=bits(f,212,32);need(assembly[n][v]<0,"interleaved packets in VN");
   need(packets.count(id),"unknown packet received");auto&p=packets.at(id);
   need(p.src==int(bits(f,244,4))&&p.dst==n&&p.op==int(bits(f,252,4)),"header corrupted");
   need(p.bytes==int(bits(f,196,16)),"length corrupted");need(p.txn==bits(f,164,32),"transaction ID corrupted");need(p.received<0,"duplicate packet");
   if(p.op==1){need(bits(f,0,32)==uint32_t(p.address),"request address corrupted");++bank_reserved[n];}
   assembly[n][v]=int(id);beat[n][v]=0;++rxslots[n][v];p.arrived=true;
   for(int k=0;k<16;k++)if(!receive_used[n][v][k]){p.receive_slot=k;receive_used[n][v][k]=true;break;}
   need(p.receive_slot>=0,"receive buffer reservation failed");if(p.op!=3)p.destination_address=0x3f0000+(v*16+p.receive_slot)*512;
  }else{
   need(assembly[n][v]>=0,"body without header");auto&p=packets.at(uint32_t(assembly[n][v]));
   int k=beat[n][v]++;need(k<int(p.body.size()),"too many body flits");Word data{};for(int i=0;i<8;i++)data[i]=f[i];
   need(data==p.body[k],"payload bit mismatch");p.got.push_back(data);
  }
  if(tail){
   auto&p=packets.at(uint32_t(assembly[n][v]));need(beat[n][v]==int(p.body.size()),"truncated packet");p.received=now;assembly[n][v]=-1;
   if(p.op==1)jobs[n][1].push_back({p.id,2,now+bankLatency});
   else if(!p.body.empty())jobs[n][v].push_back({p.id,1,now+1});
   else{p.committed=now;++done;--rxslots[n][v];receive_used[n][v][p.receive_slot]=false;}
  }
 }
 void tick(){
  d->retire_valid=0;callbacks();memory_tick();drive();d->clk=0;d->eval();
  hostAccepted=d->host_valid&&d->host_ready;
  if(d->ack_valid){lastack=now;lastok=d->ack_ok;lastackid=d->ack_id;}
  for(int n=0;n<16;n++){
   for(int v=0;v<3;v++)if((d->client_valid[n]&(1<<v))&&(d->client_ready[n]&(1<<v))){
    auto&q=source[n][v];auto&p=packets.at(q.front());
    if(p.off<0){p.sent=now;p.off=0;if(p.op==1)++outstanding[n];if(p.op!=1&&p.op!=2&&!p.body.empty())jobs[n][0].push_back({p.id,0,now+1});}
    else ++p.off;
    if(p.off>=int(p.body.size())){if(p.op==2&&p.from_bank)--bank_reserved[n];q.pop_front();}
   }
   if(d->egress_valid&(1<<n)){
    auto&f=d->egress_flit[n];if(bits(f.data(),257,1)){
     int op=bits(f.data(),252,4);uint32_t id=bits(f.data(),212,32);
     if(op!=5&&op!=6){
      auto&p=packets.at(id);need(p.inject<0,"duplicate injected header");p.inject=now;
      int expected=(p.op==1||p.op==2)?(expectedDual?1:0):p.circuit?2:0;
      need(d->egress_path[n]==expected,"incorrect type or circuit routing");
     }
    }
   }
   if(d->rx_valid&(1<<n))receive(n,d->rx_flit[n].data());
  }
  d->clk=1;d->eval();d->clk=0;d->eval();++now;
  need(d->protocol_errors<=expected_errors,"NI protocol error");
  need(now<4000000,"RTL watchdog");
 }
 void drain(){
  int until=now+1000000;
  while(done<int(packets.size())||!d->network_idle){tick();need(now<until,"drain timeout");}
  for(auto&[id,p]:packets)need(p.committed>=0,"uncommitted packet");
  for(auto&[id,p]:packets)if(p.op==3)for(size_t b=0;b<p.body.size();b++)for(int k=0;k<8;k++)
   need(memory[p.dst][p.destination_address/4+b*8+k]==p.body[b][k],"persistent MoE reassembly mismatch");
 }
 bool cfg(int dst,int action,int target,int state,int version){
  d->host_dst=dst;d->host_action=action;d->host_target=target;d->host_state=state;d->host_version=version;d->host_id=command++;
  uint32_t id=d->host_id;d->host_valid=1;int limit=now+10000;
  do{tick();need(now<limit,"configuration injection timeout");}while(!hostAccepted);
  d->host_valid=0;
  while(lastackid!=id){tick();need(now<limit,"configuration acknowledgement timeout");}
  return lastok;
 }
 void pause(){for(int n=0;n<16;n++)need(cfg(n,0,0,0,d->active_version),"pause rejected");while(d->pause_ack!=65535)tick();}
 void apply(const vector<Path>&plan){
  auto states=image(plan);int version=(d->active_version+1)&65535;
  for(int k=0;k<3;k++)d->seq_plan[k]=0;
  for(int c=0;c<13;c++)for(int bit=0;bit<6;bit++)if((states[c]>>bit)&1)d->seq_plan[(6*c+bit)/32]|=1u<<((6*c+bit)%32);
  d->seq_version=version;d->seq_start=1;int until=now+20000;
  do{bool accepted=d->seq_ready;tick();if(accepted)break;need(now<until,"sequencer admission timeout");}while(true);
  d->seq_start=0;
  while(!d->seq_done){tick();need(now<until,"configuration sequencer timeout");}
  need(!d->seq_error,"configuration sequencer rejected update");
  active_image=states;active_paths=plan;
  for(auto&[id,p]:packets)if(p.hold){p.hold=false;p.version=version;p.saved_route=false;}
 }
};
static void selftest(bool dual,int mode){
 Harness h(dual);h.backpressure=11;h.d->hiband_mode=mode;
 int pairs=0;
 for(int s=0;s<16;s++)for(int t=0;t<16;t++){
  if(mode==3&&(s/4!=t/4||abs(s%4-t%4)>1))continue;
  h.add(s,t,4,0);h.gets(s,t,0);++pairs;
 }
 h.drain();need(h.done==pairs*3,"all-pairs count");
 cout<<"PASS mode "<<mode<<" "<<pairs<<" pairs, short MoE type, causal GetS/DataS, finite storage, payload bits, random backpressure\n";
 Harness bad(dual);bad.d->hiband_mode=mode;bad.expected_errors=1;bad.gets(0,1,0);
 auto&fake=bad.add(2,0,2,64);fake.txn=1;fake.readybeats=2;
 if(mode!=3){
  for(int i=0;i<200;i++)bad.tick();
  need(bad.packets.at(0x40000001u).committed>=0&&bad.packets.at(fake.id).received<0&&bad.d->protocol_errors==1,"wrong-source response was not rejected safely");
  cout<<"PASS NI transaction matching, wrong-source DataS rejection, normal transaction retention and retirement\n";
 }
 if(!dual)return;
 Harness q(true);q.backpressure=11;q.apply({Path{5,8,{3}}});
 auto&p=q.add(5,8,3,512,0,true,3,q.d->active_version);(void)p;
 for(int i=0;i<64;i++)q.gets(i%8,(i%8+1)%8,q.now+i);
 q.drain();need(q.d->cs_flits==17,"CS packet framing");
 q.pause();int old=q.d->active_version;
 need(!q.cfg(0,2,0,0,old+1),"partial configuration accepted");
 need(q.d->active_version==old&&q.d->paused==65535,"failed update changed version or resumed");
 for(int c=0;c<13;c++){
  int owner=c<9?4*(c/3)+c%3:c==9?0:c==10?2:c==11?8:10;
  int state=c==9||c==12?32:c==10||c==11?36:0;
  need(q.cfg(owner,1,c,state,old+1),"cycle staging failed");
 }
 need(!q.cfg(0,2,0,0,old+1),"cyclic configuration accepted");
 need(q.d->active_version==old&&q.d->paused==65535,"cycle rejection changed active state");
 for(int n=0;n<16;n++)need(q.cfg(n,4,0,0,old),"explicit consistent restore");
 q.apply({Path{5,0,{0}},Path{5,8,{3}}});
 q.add(5,0,3,512,q.now,true,0,q.d->active_version);q.add(5,8,3,512,q.now,true,3,q.d->active_version);q.drain();
 q.apply({Path{0,5,{0}},Path{8,5,{3}}});
 q.add(0,5,3,512,q.now,true,0,q.d->active_version);q.add(8,5,3,512,q.now,true,3,q.d->active_version);q.drain();
 cout<<"PASS CS3 NE-to-SW, shared NI source/destination, networked pause/write/commit/install/resume, failed update retention\n";
 for(int c=0;c<9;c++)for(int a=0;a<4;a++)for(int b=0;b<4;b++)if(a!=b){
  Path path{peer(c,a),peer(c,b),{c}};q.apply({path});q.add(path.src,path.dst,3,32,q.now,true,c,q.d->active_version);q.drain();
 }
 for(int s:{0,2,8,10})for(int t:{0,2,8,10})if(s!=t){auto ps=paths(s,t);int count=0;for(auto&path:ps)if(path.cs.size()>1&&count++<2){q.apply({path});q.add(s,t,3,32,q.now,true,path.cs[0],q.d->active_version);q.drain();}}
 cout<<"PASS 108 directed lower CS paths and 24 upper-network paths\n";
 q.apply({Path{5,8,{3}}});q.block_node=8;q.block_until=q.now+2000;
 q.add(5,8,3,512,q.now,true,3,q.d->active_version);
 for(int i=0;i<40;i++)q.tick();q.pause();
 need(!q.d->cs_idle,"expected blocked in-flight circuit");
 int coherent=q.done;for(int i=0;i<8;i++)q.gets(0,1,q.now+i*3);
 for(int i=0;i<180;i++)q.tick();need(q.done>=coherent+16,"coherence stopped while CS paused");
 need(!q.cfg(0,2,0,0,q.d->active_version+1),"commit accepted before drain");
 q.block_until=q.now;while(!q.d->cs_idle)q.tick();
 for(int n=0;n<16;n++)need(q.cfg(n,4,0,0,q.d->active_version),"restore after busy rejection");q.drain();
 auto&stale=q.add(5,8,3,32,q.now,true,3,q.d->active_version+1);uint32_t staleid=stale.id;
 for(int i=0;i<20;i++)q.tick();need(q.packets.at(staleid).sent<0,"stale descriptor admitted");
 q.packets.at(staleid).circuit=false;q.drain();
 cout<<"PASS directed cycle rejection, drain-before-commit under backpressure, coherence progress while paused, stale version hold\n";
}
struct InputWave{string stage;int H;vector<array<int,3>> flows,gets;};
#include "controller.h"
static vector<InputWave> loadcase(const string&name){
 ifstream f(name);int count;f>>count;need(bool(f),"case open failed");vector<InputWave> out;
 for(int i=0;i<count;i++){
  InputWave w;int nf,ng;f>>w.stage>>nf>>ng>>w.H;
  for(int j=0;j<nf;j++){array<int,3>a;f>>a[0]>>a[1]>>a[2];w.flows.push_back(a);}
  for(int j=0;j<ng;j++){array<int,3>a;f>>a[0]>>a[1]>>a[2];w.gets.push_back(a);}out.push_back(w);
 }
 need(bool(f),"malformed case");return out;
}
static vector<Path> construct(const InputWave&w){
 map<pair<int,int>,int> volume;for(auto f:w.flows)volume[{f[0],f[1]}]+=f[2];
 vector<pair<int,pair<int,int>>> order;for(auto[sd,b]:volume)order.push_back({-b,sd});sort(order.begin(),order.end());
 vector<Path> selected;int occupied=0;
 // Bounded volume construction; see planner.py for the candidate pool and
 // packet-resource audit. This forced path is a mechanism control, not a guard.
 for(auto [neg,sd]:order){auto ps=paths(sd.first,sd.second);if(ps.size()>2)ps.resize(2);
  for(auto&p:ps){int mask=0;for(auto c:p.cs)mask|=1<<c;if(!(mask&occupied)){selected.push_back(p);occupied|=mask;break;}}
 }
 return selected;
}
static void benchmark(const string&file,const string&arm,bool dual,int mode,int banklat,int clockns){
 auto waves=loadcase(file);vector<string> results;long long allread=0,allwrite=0,allbank=0;
 auto begin=chrono::steady_clock::now();
 for(auto&w:waves){
  Harness h(dual);h.d->hiband_mode=mode;h.bankLatency=banklat;h.clock_ns=clockns;
  bool onlyGets=arm=="gets_only",onlyMoe=arm=="moe_only";
  bool force=arm=="forced_cs",runtime=arm=="runtime";
  auto hoststart=chrono::steady_clock::now();vector<Path> plan=force?construct(w):vector<Path>{};
  long long planning_ns=chrono::duration_cast<chrono::nanoseconds>(chrono::steady_clock::now()-hoststart).count();
  if(onlyGets)for(auto f:w.flows)h.nextid+=(f[2]+511)/512;
  for(auto f:w.flows)if(!onlyGets)for(int off=0;off<f[2];off+=512){
   Path* chosen=nullptr;for(auto&p:plan)if(p.src==f[0]&&p.dst==f[1]){chosen=&p;break;}
   auto&p=h.add(f[0],f[1],3,min(512,f[2]-off));
   if(chosen&&force){p.circuit=true;p.cs=chosen->cs[0];p.hold=true;}
  }
  for(auto g:w.gets)if(!onlyMoe)h.gets(g[1],g[2],g[0]);
  int setup_begin=-1,setup_end=-1;bool late=false;
  if(force&&!plan.empty()){
   setup_begin=h.now;h.apply(plan);setup_end=h.now;
  }
  PolicyReceipt policy;
  if(runtime){policy=runtime_policy(h,w.H);planning_ns=policy.host_ns;late=policy.late;plan.clear();}
  h.drain();if(!dual)need(h.d->hiband_mode_ready||mode==0,"HiBand mode was not acknowledged");
  int mt=0,ct=0;vector<int> lat;long long niwait=0;
  uint64_t canonical=1469598103934665603ull;
  for(auto&[id,p]:h.packets){
   if(p.op==3||p.op==4)mt=max(mt,p.committed);
   if(p.op==2){ct=max(ct,p.committed);auto&request=h.packets.at(p.txn);lat.push_back(p.committed-request.at);niwait+=request.inject-request.at;}
   for(auto&w:p.got)for(auto x:w){canonical^=x;canonical*=1099511628211ull;}
  }
  sort(lat.begin(),lat.end());int p99=lat.empty()?0:lat[(lat.size()*99+99)/100-1];
  long long expectedRead=0,expectedWrite=0;
  for(auto&[id,p]:h.packets){if(p.op==3)expectedRead+=p.body.size();if(p.op==3||p.op==2)expectedWrite+=p.body.size();}
  need(h.source_services==expectedRead&&h.dest_services==expectedWrite,"SRAM service count mismatch");
  need(h.bank_services==lat.size()*2,"GetS bank read count mismatch");
  allread+=h.source_services;allwrite+=h.dest_services;allbank+=h.bank_services;
  ostringstream s;s<<"{\"stage\":\""<<w.stage<<"\",\"finish\":"<<max(mt,ct)<<",\"moe\":"<<mt<<",\"gets\":"<<ct<<",\"gets_p99\":"<<p99<<",\"gets_count\":"<<lat.size()<<",\"gets_injection_wait_sum\":"<<niwait<<",\"packets\":"<<h.packets.size()<<",\"canonical_payload_hash\":\""<<hex<<canonical<<dec<<"\",\"m_flits\":"<<h.d->m_flits<<",\"c_flits\":"<<h.d->c_flits<<",\"cs_flits\":"<<h.d->cs_flits<<",\"configuration_requests\":"<<h.d->config_flits<<",\"setup_begin\":"<<setup_begin<<",\"setup_end\":"<<setup_end<<",\"planner_ns\":"<<planning_ns<<",\"decision_late\":"<<(late?"true":"false")<<",\"selected_paths\":"<<plan.size()<<",\"candidates\":"<<policy.candidates<<",\"evaluated\":"<<policy.evaluated<<",\"installed\":"<<(policy.installed?"true":"false")<<",\"policy_reason\":\""<<policy.reason<<"\"}";
  results.push_back(s.str());
 }
 auto elapsed=chrono::duration_cast<chrono::milliseconds>(chrono::steady_clock::now()-begin).count();
 cout<<"{\"status\":\"PASS_RTL_DELIVERY_PAYLOAD_AND_SRAM\",\"arm\":\""<<arm<<"\",\"dual\":"<<dual<<",\"hiband_mode\":"<<mode<<",\"bank_latency\":"<<banklat<<",\"clock_ns\":"<<clockns<<",\"read_flits\":"<<allread<<",\"write_flits\":"<<allwrite<<",\"bank_flits\":"<<allbank<<",\"wall_ms\":"<<elapsed<<",\"runtime_status\":\""<<(arm=="runtime"?"EXACT_RTL_MODEL_WITH_CHARGED_CPU_TIME":"NOT_RUNTIME_POLICY")<<"\",\"waves\":[";
 for(size_t i=0;i<results.size();i++){if(i)cout<<",";cout<<results[i];}cout<<"]}\n";
}
int main(int argc,char**argv){
 try{cout.setf(ios::unitbuf);Verilated::commandArgs(argc,argv);bool dual=true;int mode=0;
  for(int i=1;i<argc;i++){if(string(argv[i])=="--shared")dual=false;if(string(argv[i])=="--mode"&&i+1<argc)mode=stoi(argv[++i]);}
  if(argc>1&&string(argv[1])=="--selftest"){selftest(dual,mode);return 0;}
  if(argc>1&&string(argv[1])=="--controller-test"){controller_test();return 0;}
  if(argc>3&&string(argv[1])=="--case"){
   (void)legal_paths(0,1); // Static physical-path enumeration is offline.
   string arm=argv[3];int bank=8,clockns=1;
   for(int i=4;i<argc;i++){if(string(argv[i])=="--bank"&&i+1<argc)bank=stoi(argv[++i]);if(string(argv[i])=="--clock-ns"&&i+1<argc)clockns=stoi(argv[++i]);}
   need(clockns>0,"clock period must be positive");benchmark(argv[2],arm,dual,mode,bank,clockns);return 0;
  }
  throw runtime_error("usage --selftest [--shared]");
 }catch(exception&e){cerr<<"FAIL "<<e.what()<<'\n';return 1;}
}

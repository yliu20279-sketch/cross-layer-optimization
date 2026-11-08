#include "receive_ready.h"
#include "program_fences.h"
#include "../configuration.h"
#include "../sim_foundation.h"
#include "../mess_queue.h"
#include <algorithm>
#include <cstdlib>
#include <iomanip>
#include <stdexcept>
#include <string>

namespace {void need(bool b,const char*s){if(!b)throw std::runtime_error(std::string("Receive-ready: ")+s);}}
ReceiveReady&ReceiveReady::get(){static ReceiveReady x;return x;}
ReceiveReady::ReceiveReady(){
    const char*p=std::getenv("NOC_RECEIVE_READY");if(!p)return;
    need(std::string(p)=="1","mode must be 1 or unset");enabled_=true;
    need(std::getenv("NOC_DATA_WIRE")&&std::getenv("NOC_RECEIVE_POSTS"),"requires wire and actual READ calendar");
    need(configuration::ap().virtual_channel_number()==3,"requires the fixed 3-VC budget");
    need(!std::getenv("NOC_QUIESCENT_SKIP")||std::string(std::getenv("NOC_QUIESCENT_SKIP"))=="0","skip unvalidated with readiness");
    log_.open("receive_ready_events.csv");need(bool(log_),"cannot open audit");
    log_<<std::setprecision(17)<<"time,event,node,message_id,detail\n";
}
unsigned ReceiveReady::hash(std::uint64_t id){id^=id>>33;id*=0xff51afd7ed558ccdULL;id^=id>>33;return unsigned(id)&(SLOTS-1);}
void ReceiveReady::record(time_type t,const char*e,long n,std::uint64_t id,long d){log_<<t<<','<<e<<','<<n<<','<<id<<','<<d<<'\n';}
void ReceiveReady::register_router(long n,sim_router_template*r){if(enabled_)routers_.at(n)=r;}
void ReceiveReady::start(){
    if(!enabled_)return;need(!started_,"duplicate start");started_=true;
    for(const auto&v:ReceiveContract::get().posted_views()){
        need(v.id&&v.metadata&&v.address+v.bytes<=BASE&&v.metadata+32<=BASE,"receive region overlaps reserved grant table or lacks descriptor");
        posts_[v.destination].push_back(v);++total_;
    }
    need(total_>0,"no posted receives");
    for(int n=0;n<16;++n){need(routers_[n],"missing target router");
        std::stable_sort(posts_[n].begin(),posts_[n].end(),[](const auto&a,const auto&b){return a.ready<b.ready;});}
}
bool ReceiveReady::source_pending(long n)const{
    auto&r=*routers_[n];for(long v=1;v<3;++v)if(r.input_module().state(0,v)==SW_TR_)return true;
    return false;
}
bool ReceiveReady::idle_until(time_type now,time_type&limit)const{
    if(!enabled_)return false;
    for(int n=0;n<16;++n){
        if(initialized_[n]!=SLOTS||!inbox_[n].empty()||descriptor_read_[n]||lookup_[n].id)return false;
        if(next_[n]<posts_[n].size()){
            const auto&p=posts_[n][next_[n]];
            const auto issue=ProgramFences::get().issue_time(n,p.id,false,long(p.ready));
            if(issue<0)return false;
            const time_type ready=issue+1;
            if(ready<=now+1)return false;
            limit=std::min(limit,ready);
        }
    }
    return true;
}
bool ReceiveReady::memory(long n,time_type t,unsigned slot,const char*e){
    need(slot<SLOTS,"table index out of range");
    return !source_pending(n)&&ReceiveContract::get().protocol_sram(n,t,BASE+32*slot,e);
}
bool ReceiveReady::is_notice(const flit_template&f){
    return f.type()==SINGLE&&f.data().size()==4&&(f.data()[3]>>61)==4;
}
bool ReceiveReady::can_accept(long n)const{return inbox_.at(n).size()<INBOX;}
bool ReceiveReady::consume(long n,time_type t,const flit_template&f){
    if(!enabled_||!is_notice(f))return false;
    const auto&d=f.data();const auto receiver=long((d[3]>>53)&15),sender=long((d[3]>>57)&15);
    need(d[0]&&d[1]&&d[2]==0&&(d[3]&((std::uint64_t(1)<<53)-1))==0,"invalid serialized notice");
    need(sender==n&&f.des_addr()==add_type{n}&&f.sor_addr()==add_type{receiver},"notice address mismatch");
    need(can_accept(n),"finite control inbox overflow");
    need(++accepted_[d[0]]==1,"duplicate notice");
    inbox_[n].push_back({d[0],d[1],receiver,t+1,hash(d[0]),0,false});
    ++received_;max_inbox_=std::max<long>(max_inbox_,inbox_[n].size());record(t,"NOTICE_RECEIVED",n,d[0],receiver);
    return true;
}
void ReceiveReady::tick(long n,time_type t){
    if(!enabled_||!started_)return;
    // No free preinitialized SRAM table: clear one actual record per granted
    // SRAM service edge. NPU work retains its fixed higher priority.
    if(initialized_[n]<SLOTS){
        if(memory(n,t,initialized_[n],"GRANT_CLEAR"))++initialized_[n];
        return;
    }
    // One bounded control inbox. Hash probing and insertion really contend for
    // the one SRAM port; no associative lookup or unlimited register table.
    if(!inbox_[n].empty()){
        auto&q=inbox_[n].front();
        if(t>=q.eligible&&memory(n,t,q.slot,q.write?"GRANT_WRITE":"GRANT_PROBE")){
            auto&g=table_[n][q.slot];
            if(q.write){need(g.state!=1,"grant insertion lost reserved slot");
                g={q.id,q.bytes,q.peer,1};++occupied_[n];max_entries_=std::max<long>(max_entries_,occupied_[n]);
                record(t,"GRANT_STORED",n,q.id,q.slot);inbox_[n].pop_front();
            }else if(g.state!=1){q.write=true;q.eligible=t+1;}
            else {need(g.id!=q.id,"duplicate grant entry");need(++q.probes<SLOTS,"finite grant table full");q.slot=(q.slot+1)&(SLOTS-1);}
        }
        return;
    }
    auto&v=posts_[n];auto&i=next_[n];if(i==v.size())return;
    const auto&p=v[i];
    const auto issue=ProgramFences::get().issue_time(n,p.id,false,long(p.ready));
    if(issue<0||t<issue+1)return;
    if(!ProgramFences::get().eligible(n,p.id,false,long(t)-1))return;
    if(!descriptor_read_[n]){
        if(!source_pending(n)&&ReceiveContract::get().protocol_sram(n,t,p.metadata,"READY_DESCRIPTOR_READ")){
            descriptor_read_[n]=true;record(t,"DESCRIPTOR_READ",n,p.id,p.source);}
        return;
    }
    auto&r=*routers_[n];if(r.input_module().input(0,0).size()>=8)return;
    // Type=100, destination=original source, source=original receiver.
    Data_type data{p.id,p.bytes,0,(std::uint64_t(4)<<61)|(std::uint64_t(p.source)<<57)|(std::uint64_t(n)<<53)};
    add_type src{n},dst{p.source};const auto id=packet_id_++;
    r.inject_packet(long(id),src,dst,t,1,id,&data);
    need(++emitted_[p.id]==1,"duplicate descriptor emission");
    ++issued_;record(t,"NOTICE_SENT",n,p.id,p.source);descriptor_read_[n]=false;++i;
}
bool ReceiveReady::admit(std::size_t packet,long n,long destination,time_type t){
    if(!enabled_)return true;
    if(initialized_[n]<SLOTS)return false;
    auto trans=sim_foundation::wsf().protoEngine().get_trans(packet);
    if(trans->protoDesc&0xF0000L)return true;
    if(!ProgramFences::get().eligible(n,std::uint64_t(trans->protoDesc),true,long(t)))return false;
    const auto id=std::uint64_t(trans->protoDesc);auto&l=lookup_[n];
    if(l.id!=id)l={id,hash(id),0,0,0};
    if(l.state==2){if(t<l.eligible)return false;
        need(++admitted_[id]==1,"data admitted twice");++released_;record(t,"DATA_ADMITTED",n,id,destination);l={};return true;}
    if(!memory(n,t,l.slot,l.state==1?"GRANT_REMOVE":"GRANT_LOOKUP"))return false;
    auto&g=table_[n][l.slot];
    if(l.state==1){need(g.state==1&&g.id==id,"grant disappeared");g.state=2;--occupied_[n];l.state=2;l.eligible=t+1;return false;}
    if(g.state==1&&g.id==id){
        // READ bytes must equal the WRITE payload (first flit is metadata).
        need(g.peer==destination&&g.bytes==std::uint64_t(trans->packetSize-1)*32,"grant/source descriptor mismatch");
        l.state=1;record(t,"GRANT_MATCH",n,id,l.slot);
    }else if(g.state==0){l.slot=hash(id);l.probes=0;}
    else {need(++l.probes<SLOTS,"grant lookup exhausted table");l.slot=(l.slot+1)&(SLOTS-1);}
    return false;
}
void ReceiveReady::finish(){
    if(!enabled_)return;
    need(issued_==total_&&received_==total_&&released_==total_,"not all real notifications and data admissions completed");
    for(int n=0;n<16;++n)need(!occupied_[n]&&inbox_[n].empty(),"grant storage did not drain");
    log_.flush();std::ofstream out("receive_ready_summary.json");
    out<<"{\"state\":\"passed\",\"notifications\":"<<issued_<<",\"received\":"<<received_
       <<",\"data_admissions\":"<<released_<<",\"control_VC\":0,\"data_VCs\":[1,2],\"original_total_VCs\":3,"
       <<"\"grant_table_bytes_per_node\":131072,\"control_inbox_flits\":8,\"max_inbox\":"<<max_inbox_
       <<",\"max_grant_entries\":"<<max_entries_<<"}";
}
void ReceiveReady::forward(long n,long ip,long iv,long op,long ov,const flit_template&f,time_type t){
    if(!enabled_)return;
    const bool control=iv==0;
    if(control)need(f.type()==SINGLE&&f.data().size()==4&&(f.data()[3]>>61)>=4,"data entered reserved control VC");
    else need(iv==1||iv==2,"unexpected data VC");
    if(op<routers_[n]->physic_ports())need(control?ov==0:ov==1||ov==2,"VC class changed on a physical Mesh link");
    record(t,control?"FORWARD_CONTROL":"FORWARD_DATA",n,f.getPacketId(),(ip<<24)|(iv<<16)|(op<<8)|ov);
}

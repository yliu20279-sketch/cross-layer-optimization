#include "program_fences.h"
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <algorithm>
namespace {void need(bool b,const char*s){if(!b)throw std::runtime_error(std::string("Program fences: ")+s);}}
ProgramFences&ProgramFences::get(){static ProgramFences p;return p;}
ProgramFences::ProgramFences(){
    const char* path=std::getenv("NOC_PROGRAM_FENCES");if(!path)return;
    enabled_=true;
    const char* dm=std::getenv("NOC_DRAM_PROGRAM");dram_enabled_=dm&&std::string(dm)=="1";
    const char* clock=std::getenv("NOC_CAUSAL_COMMAND_CLOCK");
    command_clock_=clock&&std::string(clock)=="1";
    std::ifstream in(path);need(bool(in),"cannot read explicit program trace");
    for(long n=0;n<16;++n)fences_[{n,0}].actual=0;
    std::string line;
    while(std::getline(in,line)){
        std::istringstream row(line);std::string kind,extra;long n,f;
        need(bool(row>>kind>>n>>f)&&n>=0&&n<16&&f>=0,"bad trace node/fence");
        if(kind=="fence"){
            Fence v;need(f>0&&bool(row>>v.parent>>v.gap>>v.tx>>v.rx>>v.predicted),"bad blocking wait");
            need(v.parent>=0&&v.parent<f&&v.gap>=0&&(v.tx||v.rx)&&v.predicted>=0,"bad fence dependency");
            need(fences_.emplace(std::make_pair(n,f),v).second,"duplicate program wait");++wait_count_;
        }else if(kind=="dram"){
            need(dram_enabled_,"DRAM record requires exact native memory solver");
            Fence v;v.dram=true;
            need(f>0&&bool(row>>v.parent>>v.gap>>v.write>>v.address>>v.bytes>>v.request>>v.predicted),"bad actual DRAM record");
            need(v.parent>=0&&v.parent<f&&v.gap>=0&&v.bytes>0&&v.address+v.bytes<=2147483648ULL&&
                 (v.request>>48)==0x4e50&&v.predicted>=0,"bad native DRAM fields");
            need(fences_.emplace(std::make_pair(n,f),v).second,"duplicate native DRAM fence");++dram_count_;
        }else if(kind=="release"){
            std::uint64_t id;long send,off;need(bool(row>>id>>send>>off)&&id&&(send==0||send==1)&&off>=0,"bad issued command");
            need(releases_.emplace(std::make_tuple(n,id,bool(send)),Release{f,off}).second,"duplicate program issue");
        }else if(kind=="service"){
            long off,bytes,pred;need(bool(row>>off>>bytes>>pred)&&off>0&&bytes>0&&bytes<=256,"bad actual native SRAM service");
            auto it=fences_.find({n,f});need(it!=fences_.end(),"service without program fence");
            it->second.services.push_back({off,bytes,pred});++total_;
        }else need(false,"unknown program record");
        need(!(row>>extra),"trailing program fields");
    }
    // The initial fence is known at startup; every other fence is resolved
    // only by its explicit parent and its own actual TX/RX completions.
    for(auto&kv:fences_)if(kv.first.second==0)for(const auto&s:kv.second.services){
        need(s.predicted==s.offset,"initial native service mismatch");services_[{kv.first.first,s.offset}]+=s.bytes;
    }
    for(const auto&kv:fences_)if(kv.first.second>0)need(fences_.count({kv.first.first,kv.second.parent}),"missing parent fence");
    for(const auto&kv:releases_)need(fences_.count({std::get<0>(kv.first),kv.second.fence}),"issue without program fence");
    if(dram_enabled_){
        const char* cfg=std::getenv("NOC_DRAM_CONFIG");need(cfg&&*cfg,"missing actual DRAM configuration");
        need(std::string(std::getenv("LEGOSIM_HB_SERVICE_BYTES")?std::getenv("LEGOSIM_HB_SERVICE_BYTES"):"")=="128"&&
             std::string(std::getenv("LEGOSIM_HB_SERVICE_CYCLES")?std::getenv("LEGOSIM_HB_SERVICE_CYCLES"):"")=="5","frozen HB ratio not enabled");
        for(long n=0;n<16;++n){
            dram_[n]=std::make_unique<memory::Ramulator2Wrapper>(cfg);
            need(dram_[n]->transactionBytes()==32&&dram_[n]->clockPeriodNs()==1.25,"native memory geometry/clock changed");
        }
        dram_log_.open("dram_program_queries.csv");
        dram_log_<<"node,request_id,write,address,bytes,issue,arrival,service_start_tick,service_end_tick,service_done,actual,nominal\n";
        for(const auto&kv:fences_)if(kv.first.second>0){
            const auto n=kv.first.first;const auto f=kv.first.second;const auto&v=kv.second;
            children_[{n,v.parent}].push_back(f);
            if(v.tx)waiters_[{n,v.tx,true}].push_back(f);
            if(v.rx)waiters_[{n,v.rx,false}].push_back(f);
            if(v.parent==0)pending_.push_back(kv.first);
        }
        resolve_memory();
    }
}
void ProgramFences::resolve(){
    if(dram_enabled_){resolve_memory();return;}
    for(auto&kv:fences_){
        auto&v=kv.second;if(v.actual>=0)continue;const auto n=kv.first.first;
        const auto&p=fences_.at({n,v.parent});if(p.actual<0)continue;
        auto a=completed_.find({n,v.tx,true}),b=completed_.find({n,v.rx,false});
        if((v.tx&&a==completed_.end())||(v.rx&&b==completed_.end()))continue;
        v.actual=std::max({p.actual+v.gap,v.tx?a->second:0L,v.rx?b->second:0L});
        for(const auto&s:v.services){
            const auto t=v.actual+s.offset;auto&uses=services_[{n,t}];uses+=s.bytes;
            need(uses<=256,"retimed native services overbook configured SRAM");
            moved_+=t!=s.predicted;
        }
    }
}
void ProgramFences::resolve_memory(){
    auto occupancy=[](std::uint64_t b){return (b*5+127)/128;};
    while(!pending_.empty()){
        const auto key=pending_.front();pending_.pop_front();auto&v=fences_.at(key);
        if(v.actual>=0)continue;
        const auto n=key.first;const auto&p=fences_.at({n,v.parent});if(p.actual<0)continue;
        if(v.dram){
            const auto issue=p.actual+v.gap;
            const auto arrival=issue+occupancy(32)+(v.write?occupancy(v.bytes):0);
            const auto got=dram_[n]->runAtGlobal(v.write,v.address,v.bytes,arrival,1.25);
            v.actual=got.global_done_cycle+occupancy(v.write?16:v.bytes);
            need(v.actual>issue,"native memory completion is not causal");
            dram_changed_+=v.actual!=v.predicted;
            dram_log_<<n<<','<<v.request<<','<<v.write<<','<<v.address<<','<<v.bytes<<','<<issue<<','<<arrival
                <<','<<got.start_tick<<','<<got.end_tick<<','<<got.global_done_cycle<<','<<v.actual<<','<<v.predicted<<'\n';
        }else{
            const auto a=completed_.find({n,v.tx,true}),b=completed_.find({n,v.rx,false});
            if((v.tx&&a==completed_.end())||(v.rx&&b==completed_.end()))continue;
            v.actual=std::max({p.actual+v.gap,v.tx?a->second:0L,v.rx?b->second:0L});
        }
        for(const auto&s:v.services){
            const auto t=v.actual+s.offset;auto&uses=services_[{n,t}];uses+=s.bytes;
            need(uses<=256,"native memory solver overbooked SRAM");moved_+=t!=s.predicted;
        }
        const auto children=children_.find(key);
        if(children!=children_.end())for(auto f:children->second)pending_.push_back({n,f});
    }
}
bool ProgramFences::busy(long n,long t)const{
    auto i=services_.find({n,t});return i!=services_.end()&&i->second;
}
long ProgramFences::issue_time(long n,std::uint64_t id,bool send,long fallback)const{
    if(!command_clock_)return fallback;
    auto i=releases_.find({n,id,send});need(i!=releases_.end(),"command clock missing explicit native release");
    const auto&f=fences_.at({n,i->second.fence});
    return f.actual<0?-1:f.actual+i->second.offset;
}
bool ProgramFences::eligible(long n,std::uint64_t id,bool send,long now){
    if(!enabled_)return true;auto i=releases_.find({n,id,send});
    if(i==releases_.end())return true;
    const auto&f=fences_.at({n,i->second.fence});
    if(f.actual>=0&&now>=f.actual+i->second.offset)return true;
    ++deferred_;return false;
}
void ProgramFences::complete(long n,std::uint64_t id,bool send,long now){
    if(!enabled_)return;
    need(completed_.emplace(std::make_tuple(n,id,send),now).second,"duplicate actual completion");
    if(dram_enabled_){
        const auto found=waiters_.find({n,id,send});
        if(found!=waiters_.end())for(auto f:found->second)pending_.push_back({n,f});
    }
    resolve();
}
void ProgramFences::finish(){
    if(!enabled_)return;for(const auto&kv:fences_)need(kv.second.actual>=0,"unresolved actual program wait");
    long counted=0;for(const auto&kv:fences_)counted+=kv.second.services.size();need(counted==total_,"lost native service");
    if(command_clock_){
        std::ofstream commands("causal_command_times.csv");
        commands<<"node,descriptor,send,nominal,actual\n";
        for(const auto&kv:releases_){
            const auto n=std::get<0>(kv.first);const auto id=std::get<1>(kv.first);const auto send=std::get<2>(kv.first);
            const auto&f=fences_.at({n,kv.second.fence});
            commands<<n<<','<<id<<','<<send<<','<<f.predicted+kv.second.offset<<','<<f.actual+kv.second.offset<<'\n';
        }
    }
    if(dram_enabled_){dram_log_.flush();need(bool(dram_log_),"DRAM query trace write failed");}
    std::ofstream out("program_fences_summary.json");
    out<<"{\"state\":\"passed\",\"native_service_records\":"<<total_<<",\"retimed_services\":"<<moved_
       <<",\"release_deferrals\":"<<deferred_<<",\"explicit_waits\":"<<wait_count_;
    if(dram_enabled_)out<<",\"actual_native_DRAM_requests\":"<<dram_count_<<",\"retimed_DRAM_completions\":"<<dram_changed_;
    out<<"}";
}

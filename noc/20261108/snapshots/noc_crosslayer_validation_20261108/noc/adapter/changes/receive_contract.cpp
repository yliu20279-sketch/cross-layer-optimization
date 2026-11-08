#include "receive_contract.h"
#include "program_fences.h"
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <sstream>
#include <stdexcept>
#include <string>
#include <iomanip>
namespace{void check(bool ok,const char*s){if(!ok)throw std::runtime_error(std::string("Receive contract: ")+s);}}
long ReceiveContract::edge(time_type t){check(std::abs(t-std::round(t))<1e-8,"requires explicit common integer-cycle clock");return std::lround(t);}
ReceiveContract&ReceiveContract::get(){static ReceiveContract c;return c;}
ReceiveContract::NISlot& ReceiveContract::current(long n,long t)const{
    check(n>=0&&n<16,"invalid SRAM arbitration node");
    auto&v=ni_[n];check(t>=v.time,"NI arbitration revisited a past edge");
    if(t!=v.time)v=NISlot{t,0,0};return v;
}
long ReceiveContract::local_bytes(long n,long t)const{
    if(ProgramFences::get().enabled())return ProgramFences::get().busy(n,t)?256:0;
    auto i=local_.find({n,t});return i==local_.end()?0:i->second;
}
std::vector<ReceiveContract::PostedView> ReceiveContract::posted_views()const{
    std::vector<PostedView> rows;
    for(const auto& kv:posts_){const auto&p=kv.second;
        rows.push_back({kv.first.first,p.source,kv.first.second,p.bytes,p.address,p.metadata,p.ready});}
    return rows;
}
bool ReceiveContract::protocol_sram(long n,time_type t,std::uint64_t address,const char* event){
    check(enabled_&&npu_first_,"ready protocol requires the fixed NPU-first shared port");
    check(address<=4194304-32,"protocol access outside SRAM");
    const auto cycle=edge(t);auto&v=current(n,cycle);
    if(local_bytes(n,cycle)||v.source||v.writes)return false;
    v.writes=32;
    log_<<cycle<<','<<event<<','<<n<<",0,"<<address<<",32,-1\n";
    return true;
}
ReceiveContract::ReceiveContract(){
    source_snapshot_edge_.fill(-1);
    const char*path=std::getenv("NOC_RECEIVE_POSTS");if(!path)return;
    const char*policy=std::getenv("NOC_SRAM_POLICY");
    noc_first_=policy&&std::string(policy)=="noc_first";
    npu_first_=policy&&std::string(policy)=="npu_first";
    check(!policy||noc_first_||npu_first_,"unsupported SRAM arbitration policy");
    enabled_=true;std::ifstream input(path);check(bool(input),"cannot open actual event calendar");
    std::string line;
    while(std::getline(input,line)){
        std::istringstream row(line);std::string kind,extra;if(!(row>>kind))continue;
        if(kind=="post"){
            long d,s;std::uint64_t id,bytes,address;double t;
            check(bool(row>>d>>s>>id>>t>>bytes>>address),"bad READ descriptor");
            check(d>=0&&d<16&&s>=0&&s<16&&id&&bytes&&t>=0,"bad READ fields");
            check(address<4194304&&bytes<=4194304-address,"receive allocation outside configured 4MiB SRAM");
            check(posts_.emplace(std::make_pair(d,id),Post{s,t,bytes,address}).second,"duplicate message ID");
        }else if(kind=="descriptor"){
            long d;std::uint64_t id,address;
            check(bool(row>>d>>id>>address),"bad descriptor address");
            auto it=posts_.find({d,id});check(it!=posts_.end()&&!it->second.metadata,"descriptor without unique prior post");
            check(address&&address<=4194304-32,"descriptor outside SRAM");it->second.metadata=address;
        }else if(kind=="use"){
            long n,t,bytes;check(bool(row>>n>>t>>bytes),"bad actual NPU service edge");
            check(n>=0&&n<16&&t>0&&bytes>0&&bytes<=256,"invalid NPU service edge");
            auto&v=local_[{n,t}];v+=bytes;check(v<=256,"NPU actual service already overbooks SRAM");
        }else if(kind=="busy"){
            long n,start,finish,bytes;check(bool(row>>n>>start>>finish>>bytes),"bad local SRAM event");
            check(n>=0&&n<16&&start>=0&&finish>=start&&bytes>=0,"invalid local SRAM event");
            check(finish-start==(bytes+255)/256,"calendar does not match configured 256B/cycle");
            for(long t=start+1;t<=finish;++t){
                auto&v=local_[{n,t}];v+=std::min<long>(256,bytes-256*(t-start-1));check(v<=256,"NPU calendar already overbooks SRAM");
            }
        }else check(false,"unknown calendar record");
        check(!(row>>extra),"trailing calendar fields");
    }
    check(!posts_.empty(),"no actual READ requests");log_.open("receive_events.csv");check(bool(log_),"cannot open receive audit");
    log_<<std::setprecision(17);
    log_<<"time,event,node,message_id,address,bytes,source\n";
}
void ReceiveContract::source_snapshot(long n,time_type t,bool busy){
    if(!enabled_||(!noc_first_&&!npu_first_))return;
    source_snapshot_edge_[n]=edge(t);source_snapshot_busy_[n]=busy;
}
bool ReceiveContract::source_can_read(long n,time_type t)const{
    if(!enabled_||!npu_first_)return true;
    const auto cycle=edge(t);const auto&v=current(n,cycle);
    return !local_bytes(n,cycle)&&!v.writes&&!v.source;
}
void ReceiveContract::source_read(long n,time_type t){
    if(!enabled_)return;const auto cycle=edge(t);auto&v=current(n,cycle);v.source+=32;
    if(noc_first_)check(v.source==32&&!v.writes,"source/read and receive/write share one SRAM port");
    if(npu_first_)check(!local_bytes(n,cycle)&&v.source==32&&!v.writes,"source NI overlaps NPU/NI on the single SRAM port");
    if(local_bytes(n,cycle)+v.source+v.writes>256)++source_overbook_;
}
bool ReceiveContract::ready(long d,std::uint64_t id,long s,time_type t,bool payload,long predicted_source_bytes){
    if(!enabled_||!id)return true;
    auto it=posts_.find({d,id});check(it!=posts_.end(),"serialized Message ID has no actual READ descriptor");
    const auto&p=it->second;check(p.source==s&&!p.done,"READ source/completion mismatch");
    const auto posted=ProgramFences::get().issue_time(d,id,false,long(p.ready));
    if(posted<0||t+1e-8<posted){++waits_post_;return false;}
    if(payload||(npu_first_&&p.metadata)){const auto cycle=edge(t);auto&v=current(d,cycle);
        if(npu_first_&&local_bytes(d,cycle)){++waits_sram_;return false;}
        if(noc_first_||npu_first_){
            const bool pending=source_snapshot_edge_[d]==cycle?source_snapshot_busy_[d]:predicted_source_bytes>0;
            if(pending||v.source||v.writes){++waits_sram_;return false;}
            return true;
        }
        if(local_bytes(d,cycle)+std::max(v.source,predicted_source_bytes)+v.writes+32>256){++waits_sram_;return false;}}
    return true;
}
time_type ReceiveContract::post_time(long d,std::uint64_t id)const{
    auto it=posts_.find({d,id});
    if(it==posts_.end()||it->second.done||!id)return -1;
    return ProgramFences::get().issue_time(d,id,false,long(it->second.ready));
}
void ReceiveContract::retire(long d,std::uint64_t id,long s,time_type t,bool payload,long ordinal,bool tail){
    if(!enabled_||!id)return;
    auto it=posts_.find({d,id});check(it!=posts_.end(),"missing READ on retirement");auto&p=it->second;
    const auto posted=ProgramFences::get().issue_time(d,id,false,long(p.ready));
    check(p.source==s&&posted>=0&&t+1e-8>=posted&&!p.done,"retirement before READ or after completion");
    if(!payload){check(!p.header&&ordinal==0,"duplicate/missing header");p.header=true;
        if(npu_first_&&p.metadata){
            const auto cycle=edge(t);auto&v=current(d,cycle);v.writes+=32;
            check(!local_bytes(d,cycle)&&!v.source&&v.writes==32,"descriptor fetch conflicts on the single SRAM port");
            log_<<t<<",METADATA_READ,"<<d<<','<<id<<','<<p.metadata<<",32,"<<s<<'\n';
        }
        log_<<t<<",HEADER,"<<d<<','<<id<<','<<p.address<<",0,"<<s<<'\n';
    }else{
        check(p.header&&std::uint64_t(ordinal)==p.written/32+1,"payload order does not match descriptor");
        check(p.written<p.bytes,"receive buffer overflow");const auto b=std::min<std::uint64_t>(32,p.bytes-p.written);
        const auto cycle=edge(t);auto&v=current(d,cycle);v.writes+=32;
        if(noc_first_||npu_first_)check(!v.source&&v.writes==32&&(!npu_first_||!local_bytes(d,cycle)),"two accesses on a single SRAM port");
        else check(local_bytes(d,cycle)+v.source+v.writes<=256,"NI write exceeded shared SRAM service");
        log_<<t<<",WRITE,"<<d<<','<<id<<','<<p.address+p.written<<','<<b<<','<<s<<'\n';p.written+=b;
    }
    if(tail){check(p.written==p.bytes,"tail before complete receive buffer");p.done=true;++finished_;ProgramFences::get().complete(d,id,false,edge(t));}
}
void ReceiveContract::finish(){
    if(!enabled_)return;check(finished_==long(posts_.size()),"not all actual READ descriptors completed");
    log_.flush();std::ofstream out("receive_summary.json");
    out<<"{\"completed_posts\":"<<finished_<<",\"wait_for_post_checks\":"<<waits_post_
       <<",\"wait_for_SRAM_checks\":"<<waits_sram_<<",\"preconvergence_source_local_overbook_edges\":"<<source_overbook_
       <<",\"NPU_calendar_from_actual_events\":true,\"message_id_from_wire_header\":true"
       <<",\"single_port_noc_first\":"<<(noc_first_?"true":"false");
    if(npu_first_)out<<",\"single_port_npu_first\":true";
    out<<"}";
}

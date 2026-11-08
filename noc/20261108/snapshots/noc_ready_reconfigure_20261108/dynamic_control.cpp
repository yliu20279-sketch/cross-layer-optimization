#include "dynamic_control.h"
#include "aux_bridge.h"
#include "../mess_queue.h"
#include "../sim_foundation.h"
#include <sstream>
#include <cstdlib>
#include <stdexcept>
#include <cmath>
#include <algorithm>
#include <iomanip>

namespace {
void check(bool v,const char*why){if(!v)throw std::runtime_error(std::string("CONTROL: ")+why);}
int owner(int c){return 4*(c/3)+c%3;}
int corner(int c,int i){return owner(c)+(i/2)*4+i%2;}
bool adjacent(int n,int c){for(int i=0;i<4;++i)if(corner(c,i)==n)return true;return false;}
}
DynamicControl&DynamicControl::get(){static DynamicControl x;return x;}
DynamicControl::DynamicControl(){
    const char*name=std::getenv("NOC_DYNAMIC_PLAN");
    if(!name||!*name)return;
    enabled_=true;
    check(std::getenv("NOC_AUX_CONFIG"),"dynamic control requires AUX datapath");
    std::ifstream in(name);check(bool(in),"plan cannot open");
    std::array<bool,9> cs_seen{};std::array<bool,16> node_seen{};
    std::array<bool,16> gate_seen{};
    std::array<std::array<bool,16>,16> demand_seen{};
    std::string line;
    while(std::getline(in,line)){
        line=line.substr(0,line.find('#'));std::istringstream row(line);std::string kind,extra;
        if(!(row>>kind))continue;
        if(kind=="timing")check(bool(row>>start_>>timeout_)&&start_>=0&&timeout_>0,"timing syntax");
        else if(kind=="application_gate_ready"){
            int v;check(bool(row>>v)&&(v==0||v==1),"gate mode syntax");application_gate_=v;
        }else if(kind=="gate"){
            int n;time_type t;check(bool(row>>n>>t)&&n>=0&&n<16&&std::isfinite(t)&&t>=0&&!gate_seen[n],"gate event syntax");
            gate_seen[n]=true;gate_time_[n]=t;
        }else if(kind=="demand"){
            int n,d;uint64_t bytes;check(bool(row>>n>>d>>bytes)&&n>=0&&n<16&&d>=0&&d<16&&bytes<=UINT32_MAX&&!demand_seen[n][d],"demand syntax/range");
            demand_seen[n][d]=true;source_demand_[n][d]=uint32_t(bytes);
        }else if(kind=="probe_drop_ready"){
            check(bool(row>>drop_ready_node_>>drop_ready_chunk_)&&drop_ready_node_>=0&&drop_ready_node_<16&&drop_ready_chunk_>=0&&drop_ready_chunk_<3,"drop ready syntax");
        }else if(kind=="probe_duplicate_ready"){
            check(bool(row>>duplicate_ready_node_>>duplicate_ready_chunk_)&&duplicate_ready_node_>=0&&duplicate_ready_node_<16&&duplicate_ready_chunk_>=0&&duplicate_ready_chunk_<3,"duplicate ready syntax");
        }
        else if(kind=="epoch")check(bool(row>>next_epoch_)&&next_epoch_>0&&next_epoch_<65536,"epoch syntax");
        else if(kind=="cs"){
            int c,v;check(bool(row>>c>>v)&&c>=0&&c<9&&!cs_seen[c],"CS plan syntax");
            cs_seen[c]=true;next_cs_[c]=v;
        }else if(kind=="node"){
            int n,t,r;check(bool(row>>n>>t>>r)&&n>=0&&n<16&&!node_seen[n],"node plan syntax");
            node_seen[n]=true;next_tx_[n]=t;next_rx_[n]=r;
        }else if(kind=="packet_epoch"){
            size_t id;int e;check(bool(row>>id>>e)&&e>=0&&e<=next_epoch_,"packet epoch syntax");
            check(packet_epoch_.emplace(id,e).second,"duplicate packet epoch");
        }else if(kind=="probe_bad_load"){int v;check(bool(row>>v)&&(v==0||v==1),"probe syntax");bad_load_=v;}
        else if(kind=="probe_stale_reply"){int v;check(bool(row>>v)&&(v==0||v==1),"probe syntax");stale_probe_=v;}
        else if(kind=="probe_duplicate_arm"){int v;check(bool(row>>v)&&(v==0||v==1),"probe syntax");duplicate_arm_probe_=v;}
        else check(false,"unknown dynamic-plan record");
        check(!(row>>extra),"extra dynamic-plan tokens");
    }
    if(application_gate_){
        check(WireProtocol::get().enabled(),"Gate-ready mode requires actual serialized control packets");
        for(bool seen:gate_seen)check(seen,"all 16 real Gate events are required");
        stage_=WAIT_READY;
    }
    for(int c=0;c<9;++c){check(cs_seen[c]&&legal_state(0,c,next_cs_[c]),"missing/illegal next CS state");objects_.push_back({owner(c),0,c,next_cs_[c]});}
    for(int n=0;n<16;++n){
        check(node_seen[n]&&legal_state(1,n,next_tx_[n])&&legal_state(2,n,next_rx_[n]),"missing/illegal next selectors");
        objects_.push_back({n,1,n,next_tx_[n]});objects_.push_back({n,2,n,next_rx_[n]});
    }
    // Validate the complete next state without installing it.
    std::array<bool,16> used_tx{},used_rx{};
    for(int c=0;c<9;++c)for(int o=0;o<4;++o){
        int f=(next_cs_[c]>>(3*o))&7;if(!f)continue;
        int i=(f&3)>=o?(f&3)+1:(f&3),g=corner(c,i),d=corner(c,o);
        check(next_tx_[g]==16+c&&next_rx_[d]==16+c,"next CS/selector mismatch");
        check(!used_tx[g]&&!used_rx[d],"next cross-CS channel conflict");used_tx[g]=used_rx[d]=true;
    }
    log_.open("control_events.csv");check(bool(log_),"control log cannot open");
    log_<<std::setprecision(17);
    log_<<"time,stage,event,node,accepted,written\n";
}
bool DynamicControl::legal_state(int kind,int target,int state)const{
    if(kind==0){
        if(target<0||target>=9||state<0||state>=4096)return false;
        bool used[4]={};
        for(int o=0;o<4;++o){int f=(state>>(3*o))&7;if(!f)continue;
            if(!(f&4)||(f&3)==3)return false;
            int i=(f&3)>=o?(f&3)+1:(f&3);if(used[i])return false;used[i]=true;}
        return true;
    }
    return target>=0&&target<16&&(state==0||(state>=16&&state<25&&adjacent(target,state&15)));
}
void DynamicControl::record(const char*what,int n,uint64_t a,uint64_t w){
    log_<<mess_queue::m_pointer().current_time()<<','<<int(stage_)<<','<<what<<','<<n<<','<<a<<','<<w<<'\n';
}
bool DynamicControl::is_control(const flit_template&f)const{
    if(WireProtocol::get().enabled())return WireProtocol::get().is_control(f);
    return enabled_&&frames_.count(f.getPacketId());
}
bool DynamicControl::admit_trace(size_t id,long source,long destination)const{
    if(!enabled_)return true;
    auto&r=AuxBridge::get().routes_;auto it=r.find(id);
    if(it==r.end()||it->second.source!=source||it->second.destination!=destination)return true;
    auto e=packet_epoch_.find(id);check(e!=packet_epoch_.end(),"AUX trace packet has no explicit epoch");
    check(e->second>=agents_[source].epoch,"unadmitted old-epoch packet would cross transition");
    return !agents_[source].frozen&&e->second==agents_[source].epoch;
}
void DynamicControl::rewrite(flit_template&f){
    if(WireProtocol::get().enabled())return; // CPU injects its already serialized SINGLE directly.
    if(!is_control(f))return;
    check(f.type()==SINGLE,"control command must use one physical flit");
    f.data()=frames_.at(f.getPacketId()).data;
}
void DynamicControl::observe(const flit_template&f,bool serialized_aux,int serialized_epoch){
    if(!enabled_||is_control(f))return;
    bool aux=WireProtocol::get().enabled()?serialized_aux:AuxBridge::get().uses_aux(f);
    if(!aux)return;
    auto&s=agents_[f.sor_addr().front()];check(!s.frozen,"new source admission after FREEZE acknowledgement");
    check((WireProtocol::get().enabled()?serialized_epoch:packet_epoch_.at(f.getPacketId()))==s.epoch,"source data epoch mismatch");
    check(s.accepted!=UINT64_MAX,"source admission count overflow");++s.accepted;
}
void DynamicControl::aux_written(const flit_template&f,int serialized_epoch){
    if(!enabled_)return;
    auto&d=agents_[f.des_addr().front()];
    check((WireProtocol::get().enabled()?serialized_epoch:packet_epoch_.at(f.getPacketId()))==d.epoch,"destination data epoch mismatch");
    check(d.written!=UINT64_MAX,"destination write count overflow");++d.written;
}
void DynamicControl::emit(int source,const Command&c,uint64_t a,uint64_t w,uint64_t flags){
    uint64_t word=(uint64_t(c.type)<<45)|(uint64_t(c.node)<<41)|(uint64_t(c.op)<<39)|
        (uint64_t(c.kind)<<37)|(uint64_t(c.target)<<33)|(uint64_t(c.epoch)<<17)|(uint64_t(c.state)<<5);
    check((word>>48)==0,"48-bit command overflow");
    size_t id=next_id_++;Data_type data{a,w,flags,word<<16};
    if(!WireProtocol::get().enabled())frames_.emplace(id,Frame{c,data});
    add_type src{source},dst{c.node};auto*r=AuxBridge::get().routers_[source];
    check(r!=nullptr,"control source router is not registered");
    r->inject_packet(long(id),src,dst,mess_queue::m_pointer().current_time(),1,id,
                    WireProtocol::get().enabled()?&data:nullptr);
    if(c.type==7){++requests_;record("REQUEST",c.node,c.op,c.kind);}
    else if(c.type==6){++responses_;record("RESPONSE",source,c.state&7,c.kind);}
    else {check(c.type==5,"unknown control message type");++notifications_;record("PHASE_NOTIFY",source,c.state,c.epoch);}
}
void DynamicControl::request(const Command&c){check(!waiting_,"overlapping CPU requests");expected_=c;waiting_=true;emit(0,c);}
bool DynamicControl::local_drained(int n)const{
    auto&b=AuxBridge::get();auto*r=b.routers_[n];if(!r)return false;
    long p=r->physic_ports();
    if(!b.aux_fifo_[n].empty()||b.inflight_[n]||b.queued_[n]||b.pending_credit_[n]||!r->output_module().outbuffers(p).empty())return false;
    if(r->output_module().counter(p,0)!=b.depth_)return false;
    if(WireProtocol::get().enabled()){
        auto* wire=dynamic_cast<AuxGraphRouter*>(r);check(wire!=nullptr,"missing per-VC wire router");
        if(wire->contains_aux_input())return false;
    }else for(long ip=0;ip<r->physic_ports();++ip)for(long vc=0;vc<r->vc_number();++vc)
        for(const auto&f:r->input_module().input(ip,vc))if(b.uses_aux(f))return false;
    return true;
}
bool DynamicControl::consume(long n,const flit_template&f){
    if(!is_control(f))return false;
    const auto&data=f.data();check(data.size()==4&&f.type()==SINGLE,"bad control framing");
    uint64_t word=data[3]>>16;
    check(!(data[3]&65535)&&!(word&31),"nonzero control padding/reserved bits");
    Command c{int(word>>45),int((word>>41)&15),int((word>>39)&3),int((word>>37)&3),
              int((word>>33)&15),int((word>>17)&65535),int((word>>5)&4095)};
    check(c.node==n&&f.des_addr()==add_type{n},"wire destination/command destination mismatch");
    if(c.type==7){check(f.sor_addr()==add_type{0},"configuration request not from host");receive_request(n,c);}
    else if(c.type==5){check(n==0,"phase notification must reach CPU gateway");receive_phase_ready(f.sor_addr().front(),c,data);}
    else {check(c.type==6&&n==0,"bad control response destination/type");receive_response(f.sor_addr().front(),c,data);}
    return true;
}
void DynamicControl::receive_request(long n,const Command&c){
    auto&a=agents_[n];int status=0;auto&b=AuxBridge::get();
    if(c.epoch!=next_epoch_)status=2;
    else if(c.kind<3){
        bool target=(c.kind==0)?c.target<9&&owner(c.target)==n:c.target==n;
        if(!target)status=3;
        else if(c.op==0){
            if(!legal_state(c.kind,c.target,c.state)||c.epoch<=a.epoch)status=4;
            else {a.pending[c.kind]={c.state,c.epoch,true,false};record("LOAD",n,c.kind,c.state);}
        }else if(c.op==2){
            auto&p=a.pending[c.kind];
            if(c.state||!p.valid||p.epoch!=c.epoch||!a.frozen||!a.permit||!local_drained(n))status=5;
            else{
                if(c.kind==0)b.cs_[c.target]=p.state;
                else if(c.kind==1)b.tx_[n]=p.state;else b.rx_[n]=p.state;
                p.valid=false;p.committed=true;record("COMMIT",n,c.kind,p.state);
            }
        }else status=6;
    }else if(c.target!=n)status=3;
    else if(c.op==0&&c.state==0){a.frozen=true;record("FREEZE",n,a.accepted,a.written);}
    else if(c.op==1&&(c.state==0||c.state==1)){
        if(!a.frozen||(c.state==1&&!local_drained(n)))status=1;
    }else if(c.op==2&&c.state==0){
        if(!a.frozen||!local_drained(n))status=1;
        else {a.permit=true;record("PERMIT",n);}
    }else if(c.op==3&&c.state==0){
        bool local_commit=a.pending[1].committed&&a.pending[2].committed;
        int row=n/4,col=n%4;if(row<3&&col<3)local_commit=local_commit&&a.pending[0].committed;
        if(a.armed_epoch==c.epoch){} // Duplicate ARM never clears new data counts.
        else if(!a.frozen||!a.permit||!local_commit||!local_drained(n))status=5;
        else{
            b.validate_connections();a.accepted=a.written=0;a.epoch=c.epoch;a.armed_epoch=c.epoch;
            record("ARM",n);
        }
    }else if(c.op==3&&c.state==1){
        if(a.armed_epoch!=c.epoch)status=5;
        else {a.frozen=false;a.permit=false;if(application_gate_)source_resume_[n]=mess_queue::m_pointer().current_time();record("RUN",n);b.routers_[n]->receive_packet();}
    }else status=6;
    Command reply=c;reply.type=6;reply.node=0;
    reply.state=status|(int(n)<<3)|((c.kind==3?(c.state&3):0)<<7);
    if(status){++rejected_;record("NACK",n,status,c.kind);}
    uint64_t flags=uint64_t(a.epoch)|(uint64_t(a.frozen)<<16)|(uint64_t(local_drained(n))<<17)|
        (uint64_t(b.aux_fifo_[n].empty())<<18);
    if(c.kind==3)emit(n,reply,a.accepted,a.written,flags);else emit(n,reply);
}
void DynamicControl::set_stage(Stage s){stage_=s;index_=0;sum_a_=sum_w_=0;stage_start_=mess_queue::m_pointer().current_time();record("STAGE");}
void DynamicControl::receive_response(long source,const Command&c,const Data_type&data){
    bool match=waiting_&&source==expected_.node&&c.op==expected_.op&&c.kind==expected_.kind&&
        c.target==expected_.target&&c.epoch==expected_.epoch&&((c.state>>3)&15)==source&&
        ((c.state>>7)&3)==(c.kind==3?(expected_.state&3):0);
    if(!match){++ignored_;record("IGNORED_RESPONSE",source);return;}
    waiting_=false;int status=c.state&7;
    if(expect_bad_){check(status==4,"illegal LOAD was not rejected");expect_bad_=false;return;}
    if(status==1&&(stage_==CREDIT||stage_==PERMIT))return;
    check(status==0,"matching control response is a NACK");
    if(stage_==RUN&&index_==0&&duplicate_arm_probe_&&!duplicate_arm_checked_){
        if(!duplicate_arm_pending_){
            duplicate_arm_pending_=true;duplicate_arm_accepted_=data[0];
            record("PROBE_DUPLICATE_ARM",0,data[0],data[1]);return;
        }
        // The probe snapshots immediately before issuing the duplicate. Real
        // data may continue to arrive while its reply travels over the Mesh.
        check(data[0]>=duplicate_arm_accepted_&&duplicate_arm_accepted_>0,"duplicate ARM reset admitted new-epoch data counts");
        check((data[2]&65535)==uint64_t(next_epoch_)&&!(data[2]&(uint64_t(1)<<16)),"duplicate ARM altered epoch/frozen state");
        duplicate_arm_pending_=false;duplicate_arm_checked_=true;record("DUPLICATE_ARM_PRESERVED",0,data[0],data[1]);
    }
    if(stage_==COUNT){sum_a_+=data[0];sum_w_+=data[1];}
    ++index_;
    int limit=(stage_==LOAD||stage_==COMMIT)?int(objects_.size()):16;
    if(index_<limit)return;
    if(stage_==COUNT){
        ++count_rounds_;record("COUNT_BARRIER",-1,sum_a_,sum_w_);
        check(sum_w_<=sum_a_,"destination writes exceed frozen source admissions");
        if(sum_a_!=sum_w_){index_=0;sum_a_=sum_w_=0;return;}
    }
    if(stage_==CREDIT)++credit_rounds_;
    set_stage(Stage(int(stage_)+1));
    if(stage_==DONE){finished_=true;record("DONE");summary(true,"completed");}
}
void DynamicControl::start(){
    if(!enabled_)return;check(!started_,"controller started twice");started_=true;
    if(application_gate_){
        record("WAIT_GATE_READY");
        for(long n=0;n<16;++n)mess_queue::wm_pointer().add_message(mess_event(gate_time_[n],PHASE_READY_,add_type{n},add_type{0},0,0));
        return;
    }
    if(stale_probe_)emit(0,{6,0,0,0,0,0,0}); // Deliberate stale reply, via the real Mesh.
    stage_start_=start_;mess_queue::wm_pointer().add_message(mess_event(start_,CONTROL_TICK_));
}
void DynamicControl::tick(time_type t){
    if(!enabled_||finished_)return;
    if(t-stage_start_>timeout_){summary(false,"stage_timeout");throw std::runtime_error("CONTROL: stage timeout; no forced commit/restart");}
    if(!waiting_&&stage_!=WAIT_READY){
        if(bad_load_&&!bad_sent_){bad_sent_=true;expect_bad_=true;request({7,0,0,0,0,next_epoch_,7});}
        else if(duplicate_arm_pending_){
            // Test-only probe: RUN does not promise immediate data admission.
            // Receive-ready grant lookup/removal uses actual SRAM edges first.
            // Wait for a nonzero sample instead of rejecting a legal zero.
            if(agents_[0].accepted>0){
                duplicate_arm_accepted_=agents_[0].accepted;
                request({7,0,3,3,0,next_epoch_,0});
            }
        }
        else if(stage_==LOAD||stage_==COMMIT){
            auto&o=objects_.at(index_);request({7,o.node,stage_==LOAD?0:2,o.kind,o.target,next_epoch_,stage_==LOAD?o.state:0});
        }else {
            int op=stage_==FREEZE?0:(stage_==COUNT||stage_==CREDIT)?1:stage_==PERMIT?2:3;
            int state=(stage_==CREDIT||stage_==RUN)?1:0;
            request({7,index_,op,3,index_,next_epoch_,state});
        }
    }
    mess_queue::wm_pointer().add_message(mess_event(t+1,CONTROL_TICK_));
}
void DynamicControl::summary(bool pass,const char*reason){
    phase_summary();
    log_.flush();std::ofstream out("dynamic_summary.json");
    out<<"{\"passed\":"<<(pass?"true":"false")<<",\"reason\":\""<<reason<<"\",\"stage\":"<<int(stage_)
       <<",\"requests\":"<<requests_<<",\"responses\":"<<responses_<<",\"nacks\":"<<rejected_
       <<",\"ignored_responses\":"<<ignored_<<",\"count_rounds\":"<<count_rounds_<<",\"credit_rounds\":"<<credit_rounds_
       <<",\"duplicate_arm_preserved\":"<<(duplicate_arm_checked_?"true":"false")
       <<",\"application_gate_ready\":"<<(application_gate_?"true":"false")
       <<",\"phase_notifications\":"<<notifications_<<",\"duplicate_notifications\":"<<duplicate_notifications_
       <<",\"time\":"<<mess_queue::m_pointer().current_time()<<",\"frozen_nodes\":";
    int frozen=0;for(const auto&a:agents_)frozen+=a.frozen;out<<frozen<<"}\n";
}
void DynamicControl::finish(){if(enabled_){check(finished_,"simulation ended before dynamic protocol completed");summary(true,"completed_and_drained");}}

void DynamicControl::phase_ready(long n){
    check(application_gate_&&n>=0&&n<16,"invalid local Gate event");
    check(std::abs(mess_queue::m_pointer().current_time()-gate_time_[n])<S_ELPS_,"Gate event emitted at wrong time");
    record("LOCAL_GATE_READY",n);
    for(int chunk=0;chunk<3;++chunk){
        if(n==drop_ready_node_&&chunk==drop_ready_chunk_)continue;
        uint64_t words[3]={};
        for(int j=0;j<6;++j){int d=chunk*6+j;if(d<16)words[j/2]|=uint64_t(source_demand_[n][d])<<(32*(j%2));}
        Command c{5,0,3,3,int(n),next_epoch_,chunk};
        emit(n,c,words[0],words[1],words[2]);
        if(n==duplicate_ready_node_&&chunk==duplicate_ready_chunk_)emit(n,c,words[0],words[1],words[2]);
    }
}
void DynamicControl::receive_phase_ready(long n,const Command& c,const Data_type& data){
    check(application_gate_&&n>=0&&n<16&&c.target==n&&c.kind==3&&c.op==3&&c.epoch==next_epoch_&&c.state>=0&&c.state<3,"invalid phase notification");
    bool duplicate=received_chunks_[n]&(1u<<c.state);
    for(int j=0;j<6;++j){
        int d=c.state*6+j;uint32_t value=uint32_t(data[j/2]>>(32*(j%2)));
        if(d>=16){check(value==0,"nonzero demand padding");continue;}
        if(duplicate)check(received_demand_[n][d]==value,"conflicting duplicate demand chunk");
        else received_demand_[n][d]=value;
    }
    if(duplicate){++duplicate_notifications_;record("PHASE_READY_DUPLICATE",n,c.state);return;}
    // Progress watchdog: a legitimate slow source must not expire merely
    // because the first source completed much earlier. Duplicates do not reset it.
    if(stage_==WAIT_READY)stage_start_=mess_queue::m_pointer().current_time();
    received_chunks_[n]|=1u<<c.state;record("CPU_DEMAND_RECEIVED",n,c.state,received_chunks_[n]);
    if(!phase_tick_started_){
        phase_tick_started_=true;stage_start_=mess_queue::m_pointer().current_time();
        mess_queue::wm_pointer().add_message(mess_event(stage_start_+1,CONTROL_TICK_));
    }
    bool all=true;for(unsigned mask:received_chunks_)all=all&&(mask==7);
    if(all&&stage_==WAIT_READY){record("ALL_DEMAND_RECEIVED");set_stage(LOAD);}
}
void DynamicControl::account_source_wait(flit_template& f){
    if(!application_gate_||is_control(f))return;
    const auto& c=WireProtocol::get().source_context(f);
    if(!c.header.auxiliary)return;
    long n=f.sor_addr().front();check(source_resume_[n]>0,"data packet admitted before source RUN");
    auto shifted=std::max(f.send_finish_time(),source_resume_[n]+f.sequence());
    if(isHeader(f.type())&&shifted>f.send_finish_time())record("SOURCE_WAIT_INCLUDED",n,f.getPacketId(),uint64_t(shifted-f.send_finish_time()));
    f.set_send_finish(shifted);
}
void DynamicControl::phase_summary()const{
    if(!application_gate_)return;
    std::ofstream out("phase_demand.json");
    out<<std::setprecision(17);
    out<<"{\"fixed_configuration_fixture\":true,\"cpu_solver_time_measured\":false,\"unit\":\"payload_bytes\",\"gate_times\":[";
    for(int n=0;n<16;++n){if(n)out<<',';out<<gate_time_[n];}out<<"],\"resume_times\":[";
    for(int n=0;n<16;++n){if(n)out<<',';out<<source_resume_[n];}out<<"],\"received_masks\":[";
    for(int n=0;n<16;++n){if(n)out<<',';out<<received_chunks_[n];}out<<"],\"cpu_received_bytes\":[";
    for(int n=0;n<16;++n){if(n)out<<',';out<<'[';for(int d=0;d<16;++d){if(d)out<<',';out<<received_demand_[n][d];}out<<']';}out<<"]}\n";
}

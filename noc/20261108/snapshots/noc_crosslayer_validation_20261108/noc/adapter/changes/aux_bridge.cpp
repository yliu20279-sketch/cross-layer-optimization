#include "aux_bridge.h"
#include "dynamic_control.h"
#include "receive_ready.h"
#include "receive_contract.h"
#include "../mess_queue.h"
#include "../sim_foundation.h"
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <sstream>
#include <stdexcept>
#include <limits>
#include <iomanip>

static void require(bool ok,const std::string&why) {
    if(!ok)throw std::runtime_error("AUX/NI: "+why);
}
static void node_ok(long n) {require(n>=0&&n<16,"node out of range");}
static long corner_node(int c,int corner) {
    return (c/3+corner/2)*4+c%3+corner%2;
}
static bool adjacent(int n,int c) {
    if(c<0||c>=9)return false;
    for(int p=0;p<4;++p)if(corner_node(c,p)==n)return true;
    return false;
}
AuxBridge&AuxBridge::get() {static AuxBridge value;return value;}
AuxBridge::Key AuxBridge::key(const flit_template&f) {
    return {f.getPacketId(),f.sor_addr().front(),f.des_addr().front(),f.start_time()};
}
long AuxBridge::ordinal(const flit_template&f) {
    require(f.sequence()>=0,"negative flit sequence");return f.sequence();
}
AuxBridge::AuxBridge() {
    connection_.fill(-1);last_mesh_enqueue_.fill(-std::numeric_limits<double>::infinity());
    const char*path=std::getenv("NOC_AUX_CONFIG");
    if(!path||!*path)return;
    enabled_=true;
    require(configuration::ap().routing_alg()==GRAPH_TOPO && configuration::ap().ary_number()==16
        && configuration::ap().cube_number()==1 && configuration::ap().flit_size()==4
        && !configuration::ap().getPacketLoss(),"requires 16-node graph, 256-bit flits, no packet loss");
    std::ifstream input(path);require(bool(input),"cannot open configuration");
    std::string line;int params=0;
    std::array<bool,9>seen_cs{};std::array<bool,16>seen_node{};
    while(std::getline(input,line)) {
        line=line.substr(0,line.find('#'));std::istringstream row(line);std::string kind,extra;
        if(!(row>>kind))continue;
        if(kind=="params") {
            require(++params==1&&bool(row>>depth_>>segment_delay_>>switch_delay_>>credit_delay_>>ni_period_),"params syntax");
        } else if(kind=="cs") {
            int c,state;require(bool(row>>c>>state)&&c>=0&&c<9&&!seen_cs[c],"cs syntax/duplicate");
            seen_cs[c]=true;cs_[c]=state;
        } else if(kind=="node") {
            int n,t,r;require(bool(row>>n>>t>>r),"node syntax");node_ok(n);
            require(!seen_node[n],"duplicate node");seen_node[n]=true;tx_[n]=t;rx_[n]=r;
        } else if(kind=="route") {
            size_t id;Route r;require(bool(row>>id>>r.source>>r.destination>>r.gateway),"route syntax");
            node_ok(r.source);node_ok(r.destination);node_ok(r.gateway);
            require(r.source!=r.destination,"AUX self-transactions not supported in this static adapter");
            require(routes_.emplace(id,r).second,"duplicate route ID");
        } else if(kind=="hold") {
            int n;double until;require(bool(row>>n>>until)&&std::isfinite(until)&&until>=0,"hold syntax");
            node_ok(n);hold_until_[n]=until; // Explicit SRAM-ready fault-injection input.
        } else require(false,"unknown configuration record: "+kind);
        require(!(row>>extra),"extra configuration tokens");
    }
    require(params==1&&depth_>0&&depth_<=32,"missing/invalid FIFO depth");
    for(double d:{segment_delay_,switch_delay_,credit_delay_,ni_period_})
        require(std::isfinite(d)&&d>0,"all timing parameters must be explicit and positive");
    validate_connections();
    const char*logpath=std::getenv("NOC_AUX_LOG");
    log_.open(logpath&&*logpath?logpath:"aux_events.csv");require(bool(log_),"event log cannot be opened");
    log_<<std::setprecision(17);
    log_<<"time,event,node,packet,source,destination,ordinal,detail\n";
}
void AuxBridge::validate_connections() {
    connection_.fill(-1);
    for(int n=0;n<16;++n)for(int value:{tx_[n],rx_[n]})
        require(value==0 || (value>=16&&value<25&&adjacent(n,value&15)),"non-adjacent/invalid selector");
    for(int c=0;c<9;++c) {
        require(cs_[c]>=0&&cs_[c]<4096,"CS state out of range");
        bool used[4]={};
        for(int o=0;o<4;++o) {
            int f=(cs_[c]>>(3*o))&7;if(!f)continue;
            require((f&4)&&(f&3)!=3,"illegal CS SEL/EN");
            int i=(f&3)>=o?(f&3)+1:(f&3);
            require(!used[i],"CS input reused");used[i]=true;
            int g=corner_node(c,i),d=corner_node(c,o);
            if(tx_[g]==16+c&&rx_[d]==16+c) {
                require(connection_[g]==-1,"gateway has multiple active outputs");connection_[g]=d;
            }
        }
    }
    bool destinations[16]={};
    for(int g=0;g<16;++g)if(connection_[g]>=0) {
        int d=connection_[g];require(!destinations[d],"multiple AUX sources share one NI receiver");destinations[d]=true;
    }
    if(!std::getenv("NOC_DYNAMIC_PLAN"))for(const auto&entry:routes_)
        require(connection_[entry.second.gateway]==entry.second.destination,"packet route does not match physical CS/selectors");
}
bool AuxBridge::uses_aux(const flit_template&f) const {
    require(!WireProtocol::get().enabled(),"forbidden global packet-table lookup in wire mode");
    auto it=routes_.find(f.getPacketId());
    return it!=routes_.end()&&f.sor_addr()==add_type{it->second.source}
        &&f.des_addr()==add_type{it->second.destination};
}
long AuxBridge::gateway(const flit_template&f) const {
    require(uses_aux(f),"missing AUX route");return routes_.at(f.getPacketId()).gateway;
}
bool AuxBridge::source_route(const flit_template& f,long& gateway) const {
    // Source-NI descriptor lookup only: it is never called by a Router.
    auto it=routes_.find(f.getPacketId());
    if(it==routes_.end()||f.sor_addr()!=add_type{it->second.source}||
       f.des_addr()!=add_type{it->second.destination})return false;
    gateway=it->second.gateway;return true;
}
void AuxBridge::register_router(long n,sim_router_template*r) {
    node_ok(n);require(!routers_[n],"router registered twice");routers_[n]=r;
    require(r->output_ports()==r->physic_ports()+1,"AUX is not output-only");
    auto&out=r->output_module();
    for(long vc=0;vc<r->vc_number();++vc) {
        long p=r->physic_ports();
        while(out.counter(p,vc)>0)out.counter_dec(p,vc);
        if(vc==0)for(int k=0;k<depth_;++k)out.counter_inc(p,vc);
    }
}
void AuxBridge::event(time_type t,const char*what,long n,const flit_template&f,long detail) {
    log_<<t<<','<<what<<','<<n<<','<<f.getPacketId()<<','<<f.sor_addr().front()<<','
        <<f.des_addr().front()<<','<<ordinal(f)<<','<<detail<<'\n';
}
void AuxBridge::observe_injection(const flit_template&f) {
    bool aux=false;long g=-1;
    if(WireProtocol::get().enabled()){
        if(!DynamicControl::get().is_control(f)){
            const auto& c=WireProtocol::get().source_context(f);
            aux=c.header.auxiliary;g=c.header.gateway;
            DynamicControl::get().observe(f,aux,c.header.epoch);
        }
    }else{
        DynamicControl::get().observe(f);aux=uses_aux(f);if(aux)g=gateway(f);
    }
    if(aux)require(connection_[g]==f.des_addr().front(),"admitted packet/active configuration mismatch");
    expected_[key(f)].push_back({f.data(),f.type(),ordinal(f)});++injected_;
    event(mess_queue::m_pointer().current_time(),"INJECT",f.sor_addr().front(),f,aux);
}
time_type AuxBridge::eligible_after(time_type arrival) const {
    // NI clock edges are k*period. Input is sampled at the first edge >=
    // arrival; an empty registered FIFO cannot retire it at that same edge.
    return (std::ceil((arrival-S_ELPS_)/ni_period_)+1)*ni_period_;
}
void AuxBridge::request_service(time_type t) {
    if(!tick_pending_) {
        tick_pending_=true;
        time_type next=(std::floor((t+S_ELPS_)/ni_period_)+1)*ni_period_;
        mess_queue::wm_pointer().add_message(mess_event(next,NI_SERVICE_));
    }
}
bool AuxBridge::mesh_ready(long n,time_type t,bool control) {
    bool ready=(control||mesh_fifo_[n].size()<size_t(depth_)) && std::abs(last_mesh_enqueue_[n]-t)>S_ELPS_;
    if(!ready)++mesh_backpressure_;return ready;
}
void AuxBridge::enqueue_mesh(long n,time_type t,const flit_template&f,std::uint64_t message_id) {
    bool control=DynamicControl::get().is_control(f);
    require(mesh_ready(n,t,control),"normal NI FIFO/port overflow");
    require(f.des_addr()==add_type{n},"normal NI premature gateway completion");
    if(WireProtocol::get().enabled()){
        if(isHeader(f.type())&&!control)require(!WireProtocol::get().decode(f).header.auxiliary,"AUX packet ejected through Mesh NI");
    }else require(!uses_aux(f),"normal NI premature gateway completion");
    if(control){
        // Classification precedes the tensor-data FIFO and SRAM-write path.
        // Control and data still share the router's one local ejection port.
        auto it=expected_.find(key(f));
        require(it!=expected_.end()&&it->second.size()==1,"missing/duplicate control flit");
        const auto&x=it->second.front();
        require(x.data==f.data()&&x.type==SINGLE&&x.ordinal==0,"control payload/framing changed in Mesh");
        expected_.erase(it);last_mesh_enqueue_[n]=t;++control_retired_;
        event(t,"CONTROL_ACCEPT",n,f,control_retired_);
        require(ReceiveReady::get().consume(n,t,f)||DynamicControl::get().consume(n,f),"control packet not decoded");
        return;
    }
    mesh_fifo_[n].push_back({f,-1,eligible_after(t),message_id});last_mesh_enqueue_[n]=t;
    max_mesh_depth_=std::max<long>(max_mesh_depth_,mesh_fifo_[n].size());
    event(t,"MESH_NI",n,f,mesh_fifo_[n].size());request_service(t);
}
void AuxBridge::transmit(long g,long port,time_type t,const flit_template&f) {
    if(WireProtocol::get().enabled()){
        auto& c=wire_tx_[g];
        if(isHeader(f.type())){
            require(!c.valid,"overlapping packets on one AUX output");c=WireProtocol::get().decode(f);
            require(!c.control&&c.header.auxiliary&&c.header.gateway==unsigned(g),"invalid serialized AUX transmit header");
            WireProtocol::get().record("AUX_TX_HEADER",g,f,c);
        }
        require(WireProtocol::matches(c,f)&&connection_[g]==long(c.header.destination),"AUX output context/physical connection mismatch");
        if(isTail(f.type()))c.valid=false;
    }else require(uses_aux(f)&&gateway(f)==g&&connection_[g]==f.des_addr().front(),"AUX transmit path mismatch");
    require(port==routers_[g]->physic_ports(),"AUX overwrote a normal port");
    ++aux_sent_;++inflight_[g];event(t,"AUX_TX",g,f,connection_[g]);
    time_type arrival=t+2*segment_delay_+switch_delay_;
    mess_queue::wm_pointer().add_message(mess_event(arrival,AUX_ARRIVAL_,add_type{g},
        f.des_addr(),port,0,f));
    check_credit_balance();
}
void AuxBridge::arrive(const mess_event&e) {
    long g=e.src().front(),d=e.des().front();const auto&f=e.get_flit();
    std::uint64_t arrival_id=0;
    if(ReceiveContract::get().enabled()){
        auto&ctx=aux_arrival_context_[d];
        if(isHeader(f.type())){require(!ctx.valid,"overlapping AUX arrival contexts");ctx=WireProtocol::get().decode(f);}
        require(WireProtocol::matches(ctx,f),"AUX body lost physical-channel header context");
        arrival_id=ctx.header.message_id;if(isTail(f.type()))ctx.valid=false;
    }
    require(connection_[g]==d&&inflight_[g]>0,"bad AUX arrival");
    if(WireProtocol::get().enabled()&&isHeader(f.type())){
        auto c=WireProtocol::get().decode(f);
        require(!c.control&&c.header.auxiliary&&c.header.gateway==unsigned(g)&&c.header.destination==unsigned(d),"CS wire delivered wrong header");
        require(c.header.epoch==unsigned(DynamicControl::get().active_epoch(d)),"CS header epoch differs from destination NI active epoch");
        WireProtocol::get().record("AUX_RX_HEADER",d,f,c);
    }
    require(aux_fifo_[d].size()<size_t(depth_),"AUX NI overflow");
    --inflight_[g];++queued_[g];aux_fifo_[d].push_back({f,g,eligible_after(e.event_start()),arrival_id});
    max_aux_depth_=std::max<long>(max_aux_depth_,aux_fifo_[d].size());
    event(e.event_start(),"AUX_NI",d,f,aux_fifo_[d].size());request_service(e.event_start());
    check_credit_balance();
}
void AuxBridge::service(time_type t) {
    require(tick_pending_,"unexpected NI service event");tick_pending_=false;
    bool remains=false;
    for(int d=0;d<16;++d) {
        bool queued_m=!mesh_fifo_[d].empty(),queued_a=!aux_fifo_[d].empty();
        if(!queued_m&&!queued_a)continue;
        bool m=queued_m&&mesh_fifo_[d].front().eligible<=t+S_ELPS_;
        bool a=queued_a&&aux_fifo_[d].front().eligible<=t+S_ELPS_;
        if(!m&&!a){remains=true;continue;}
        bool fresh_aux=a&&(!m||prefer_aux_[d]);
        bool take_aux=write_locked_[d]?held_aux_[d]:fresh_aux;
        if(write_locked_[d]) {
            ++held_selection_checks_;
            if(take_aux!=fresh_aux)++selection_changes_prevented_;
            require(take_aux?a:m,"stalled output source disappeared");
        }
        if(t+S_ELPS_<hold_until_[d]) {
            write_locked_[d]=true;held_aux_[d]=take_aux;
            ++ni_waits_;remains=true;continue;
        }
        if(m&&a)++shared_contention_;
        auto&q=take_aux?aux_fifo_[d]:mesh_fifo_[d];const auto&front=q.front();
        long pending_source=0;
        for(long vc=ReceiveReady::get().enabled()?1:0;vc<routers_[d]->vc_number();++vc)
            if(routers_[d]->input_module().state(0,vc)==SW_TR_)pending_source=32;
        if(!ReceiveContract::get().ready(d,front.message_id,front.flit.sor_addr().front(),t,
               !isHeader(front.flit.type()),pending_source)){
            write_locked_[d]=true;held_aux_[d]=take_aux;remains=true;continue;
        }
        Token token=q.front();q.pop_front();
        prefer_aux_[d]=!take_aux;write_locked_[d]=false;
        const auto&f=token.flit;
        ReceiveContract::get().retire(d,token.message_id,f.sor_addr().front(),t,
            !isHeader(f.type()),ordinal(f),isTail(f.type()));
        auto it=expected_.find(key(f));require(it!=expected_.end()&&!it->second.empty(),"unrecorded/duplicate NI write");
        const auto&expected=it->second.front();
        require(expected.data==f.data()&&expected.type==f.type()&&expected.ordinal==ordinal(f),"NI payload/order mismatch");
        it->second.pop_front();if(it->second.empty())expected_.erase(it);
        bool header_only=WireProtocol::get().enabled()&&isHeader(f.type());
        if(header_only){
            ++header_retired_; // Parsed NI metadata, not a tensor SRAM write.
            event(t,take_aux?"HEADER_AUX":"HEADER_MESH",d,f,token.gateway);
        }else{
            ++payload_written_;event(t,take_aux?"WRITE_AUX":"WRITE_MESH",d,f,token.gateway);
        }
        ++written_; // Aggregate NI retirement, including header parsing.
        if(take_aux) {
            int epoch=0;
            if(WireProtocol::get().enabled()){
                auto& c=wire_rx_[d];
                if(isHeader(f.type())){
                    require(!c.valid,"overlapping AUX packets at NI write");c=WireProtocol::get().decode(f);
                    require(c.header.auxiliary&&c.header.gateway==unsigned(token.gateway),"AUX NI write header mismatch");
                }
                require(WireProtocol::matches(c,f),"AUX NI body has no matching header context");
                epoch=c.header.epoch;if(isTail(f.type()))c.valid=false;
            }
            DynamicControl::get().aux_written(f,epoch);
            ++aux_written_;--queued_[token.gateway];++pending_credit_[token.gateway];
            credit_trace_[token.gateway].push_back({f.getPacketId(),f.sor_addr().front(),f.des_addr().front(),ordinal(f)});
            long p=routers_[token.gateway]->physic_ports();
            mess_queue::wm_pointer().add_message(mess_event(t+credit_delay_,CREDIT_,add_type{d},
                add_type{token.gateway},p,0));
        } else ++mesh_written_;
        // Only the FINAL NI write enters the existing completion/protocol engine.
        if(!DynamicControl::get().consume(d,f))
            sim_foundation::wsf().router(add_type{d}).finish_from_ni(t,f);
        if(isTail(f.type())) {++completed_;event(t,"COMPLETE",d,f,take_aux);}
        remains=remains||!mesh_fifo_[d].empty()||!aux_fifo_[d].empty();
    }
    if(remains)request_service(t);
    check_credit_balance();
}
bool AuxBridge::quiescent_until(time_type now,time_type& limit)const{
    if(!enabled_||ni_period_!=1||!ReceiveContract::get().skip_compatible()||DynamicControl::get().enabled())return false;
    for(int n=0;n<16;++n){
        const bool m=!mesh_fifo_[n].empty(),a=!aux_fifo_[n].empty();
        if(!m&&!a)continue;
        if(!write_locked_[n]||hold_until_[n]>now+S_ELPS_)return false;
        if((m&&mesh_fifo_[n].front().eligible>now+S_ELPS_)||(a&&aux_fifo_[n].front().eligible>now+S_ELPS_))return false;
        const auto& token=held_aux_[n]?aux_fifo_[n].front():mesh_fifo_[n].front();
        const auto ready=ReceiveContract::get().post_time(n,token.message_id);
        if(ready<=now+S_ELPS_)return false;
        limit=std::min(limit,ready);
    }
    return true;
}
bool AuxBridge::completely_idle()const{
    if(!enabled_)return false;
    for(int n=0;n<16;++n)if(!mesh_fifo_[n].empty()||!aux_fifo_[n].empty()||inflight_[n]||queued_[n]||pending_credit_[n]||write_locked_[n])return false;
    return true;
}
void AuxBridge::skip_quiescent(std::uint64_t cycles){
    for(int n=0;n<16;++n){
        const bool m=!mesh_fifo_[n].empty(),a=!aux_fifo_[n].empty();
        if(m||a){
            require(write_locked_[n],"skip requires an already locked stalled NI");
            held_selection_checks_+=cycles;
            const bool fresh=a&&(!m||prefer_aux_[n]);
            if(fresh!=held_aux_[n])selection_changes_prevented_+=cycles;
            if(m&&a)shared_contention_+=cycles;
            ReceiveContract::get().skip_post_waits(cycles);
        }
        // routing_decision tests local receive readiness once for port 0,
        // twice for other ports (credit probe then delivery probe).
        auto& r=*routers_[n];
        for(long p=0;p<r.physic_ports();++p)for(long v=0;v<r.vc_number();++v)
            if((r.input_module().state(p,v)==HOME_||r.input_module().state(p,v)==ROUTING_)&&!r.input_module().input(p,v).empty())
                mesh_backpressure_+=(p?2:1)*cycles;
    }
}
void AuxBridge::credit_received(long g,long p,long vc) {
    if(!routers_[g]||p!=routers_[g]->physic_ports())return;
    require(vc==0&&pending_credit_[g]>0,"duplicate/invalid AUX credit");
    require(!credit_trace_[g].empty(),"missing observer credit provenance");
    const auto item=credit_trace_[g].front();credit_trace_[g].pop_front();
    log_<<mess_queue::m_pointer().current_time()<<",AUX_CREDIT,"<<g<<','<<item.packet<<','
        <<item.source<<','<<item.destination<<','<<item.ordinal<<','<<routers_[g]->output_module().counter(p,vc)<<'\n';
    --pending_credit_[g];++credits_;check_credit_balance();
}
void AuxBridge::observe_credit_reservation(long g,const flit_template& f,long remaining) {
    event(mess_queue::m_pointer().current_time(),"AUX_RESERVE",g,f,remaining);
}
void AuxBridge::check_credit_balance() const {
    for(int g=0;g<16;++g)if(routers_[g]) {
        auto&r=*routers_[g];long p=r.physic_ports();
        long free=r.output_module().counter(p,0);
        long reserved=r.output_module().outbuffers(p).size()+inflight_[g]+queued_[g]+pending_credit_[g];
        require(free>=0&&free<=depth_&&reserved+free==depth_,"AUX credit conservation failure");
    }
}
void AuxBridge::finish() {
    if(!enabled_)return;
    check_credit_balance();require(expected_.empty()&&injected_==written_+control_retired_,"injected flits did not all retire");
    require(aux_sent_==aux_written_&&aux_sent_==credits_,"AUX flit/credit loss");
    for(int n=0;n<16;++n) {
        require(credit_trace_[n].empty(),"observer credits did not retire");
        require(routers_[n]&&mesh_fifo_[n].empty()&&aux_fifo_[n].empty()&&inflight_[n]==0
                &&queued_[n]==0&&pending_credit_[n]==0,"network/NI did not drain");
        require(!wire_tx_[n].valid&&!wire_rx_[n].valid,"AUX wire packet context did not retire");
        require(routers_[n]->output_module().counter(routers_[n]->physic_ports(),0)==depth_,"AUX credits not restored");
        auto&r=*routers_[n];
        for(long p=0;p<r.physic_ports();++p)for(long vc=0;vc<r.vc_number();++vc)
            require(r.input_module().inputBufSize(p,vc)==0&&r.input_module().state(p,vc)==INIT_,"native input/VC did not drain");
        for(long p=0;p<r.output_ports();++p) {
            require(r.output_module().outbuffers(p).empty()&&r.output_module().outadd(p).empty(),"native output not empty");
            for(long vc=0;vc<r.vc_number();++vc) {
                require(r.output_module().usage(p,vc)==FREE_&&r.output_module().assign(p,vc)==VC_NULL,"native VC reservation leaked");
                long expected_credit=p<r.physic_ports()?r.buffer_size():(vc==0?depth_:0);
                require(r.output_module().counter(p,vc)==expected_credit,"native output credit not restored");
            }
        }
    }
    log_.flush();
    require(header_retired_+payload_written_==written_,"NI header/payload retirement mismatch");
    std::ofstream out("bridge_summary.json");
    out<<"{\n  \"static_cs_ni_test\": "<<(DynamicControl::get().enabled()?"false":"true")
       <<",\n  \"dynamic_configuration\": "<<(DynamicControl::get().enabled()?"true":"false")<<",\n"
       <<"  \"injected_flits\": "<<injected_<<",\n  \"written_flits\": "<<written_
       <<",\n  \"control_retired_flits\": "<<control_retired_
       <<",\n  \"data_header_retired_flits\": "<<header_retired_
       <<",\n  \"payload_written_flits\": "<<payload_written_
       <<",\n  \"aux_sent\": "<<aux_sent_<<",\n  \"aux_written\": "<<aux_written_
       <<",\n  \"mesh_written\": "<<mesh_written_<<",\n  \"aux_credits_returned\": "<<credits_
       <<",\n  \"completed_packets\": "<<completed_<<",\n  \"ni_hold_waits\": "<<ni_waits_
       <<",\n  \"mesh_backpressure_checks\": "<<mesh_backpressure_
       <<",\n  \"shared_write_contention_cycles\": "<<shared_contention_
       <<",\n  \"held_selection_checks\": "<<held_selection_checks_
       <<",\n  \"selection_changes_prevented\": "<<selection_changes_prevented_
       <<",\n  \"max_aux_fifo\": "<<max_aux_depth_<<",\n  \"max_mesh_fifo\": "<<max_mesh_depth_<<"\n}\n";
    std::cout<<"PASS cs_ni_bridge injected="<<injected_<<" written="<<written_
        <<" aux="<<aux_written_<<" mesh="<<mesh_written_<<" credits="<<credits_
        <<" completed="<<completed_<<"\n";
}

AuxGraphRouter::AuxGraphRouter(long pc,long vc,long in,long out,const add_type&address,long ary,long width)
    :CGraphTopo(pc,vc,in,out,address,ary,width,1) {
    AuxBridge::get().register_router(address.front(),this);
    ReceiveReady::get().register_router(address.front(),this);
}
const WireContext& AuxGraphRouter::wire_context(long ip,long vc,const flit_template& f) const {
    auto& c=wire_contexts_[{ip,vc}];
    if(isHeader(f.type())){
        auto decoded=WireProtocol::get().decode(f);
        if(!WireProtocol::matches(c,f)){
            c=decoded;WireProtocol::get().record("ROUTER",address_.front(),f,c);
        }
    }
    require(WireProtocol::matches(c,f),"body without matching local Router input/VC context");
    return c;
}
add_type AuxGraphRouter::routing_destination(const flit_template&f,long ip,long vc) const {
    if(WireProtocol::get().enabled()){
        const auto& c=wire_context(ip,vc,f);
        return add_type{long(c.header.auxiliary?c.header.gateway:c.header.destination)};
    }
    return AuxBridge::get().uses_aux(f)?add_type{AuxBridge::get().gateway(f)}:f.des_addr();
}
bool AuxGraphRouter::local_destination(const flit_template&f,long ip,long vc) const {
    if(WireProtocol::get().enabled()){
        const auto& c=wire_context(ip,vc,f);
        return !c.header.auxiliary&&address_==add_type{long(c.header.destination)};
    }
    return !AuxBridge::get().uses_aux(f)&&address_==f.des_addr();
}
bool AuxGraphRouter::local_receive_ready(time_type t,const flit_template&f) {
    if(ReceiveReady::get().enabled()&&ReceiveReady::is_notice(f)&&!ReceiveReady::get().can_accept(address_.front()))return false;
    return AuxBridge::get().mesh_ready(address_.front(),t,DynamicControl::get().is_control(f));
}
bool AuxGraphRouter::cached_stalled_local_header(long port,long vc)const{
    if(!WireProtocol::get().enabled()||input_module_.input(port,vc).empty()||!AuxBridge::get().mesh_full(address_.front()))return false;
    auto it=wire_contexts_.find({port,vc});
    if(it==wire_contexts_.end())return false;
    const auto& context=it->second;const auto& f=input_module_.input(port,vc).front();
    return WireProtocol::matches(context,f)&&!context.control&&!context.header.auxiliary&&
        context.header.destination==static_cast<unsigned>(address_.front());
}
void AuxGraphRouter::deliver_local(time_type t,const flit_template&f) {
    AuxBridge::get().enqueue_mesh(address_.front(),t,f);
}
void AuxGraphRouter::deliver_local_context(time_type t,const flit_template&f,long ip,long vc){
    const auto id=WireProtocol::get().enabled()?wire_context(ip,vc,f).header.message_id:0;
    AuxBridge::get().enqueue_mesh(address_.front(),t,f,id);
}
void AuxGraphRouter::observe_injection(const flit_template&f) {AuxBridge::get().observe_injection(f);}
void AuxGraphRouter::routingAlg(const add_type&dst,const add_type&src,long pc,long vc) {
    const auto&f=input_module_.get_flit(pc,vc);
    if(ReceiveReady::get().enabled()&&WireProtocol::get().is_control(f)){
        // Dimension-order control routes use only existing physical Mesh
        // neighbours. Missing edges fail; no hidden control network is added.
        const long a=address_.front(),d=dst.front();
        const long next=a%4!=d%4?a+(d%4>a%4?1:-1):a+(d/4>a/4?4:-4);
        const auto it=nextHop_port_map[a].find(next);
        require(a!=d&&it!=nextHop_port_map[a].end(),"control XY neighbour missing from physical graph");
        input_module_.add_routing(pc,vc,VC_type(it->second,0));return;
    }
    bool aux=WireProtocol::get().enabled()?wire_context(pc,vc,f).header.auxiliary:AuxBridge::get().uses_aux(f);
    if(aux&&dst==address_)
        input_module_.add_routing(pc,vc,VC_type(physic_ports_,0));
    else CGraphTopo::routingAlg(dst,src,pc,vc);
}
bool AuxGraphRouter::contains_aux_input(){
    require(WireProtocol::get().enabled(),"wire drain inspection used outside wire mode");
    for(long ip=0;ip<physic_ports_;++ip)for(long vc=0;vc<vc_number_;++vc){
        auto it=wire_contexts_.find({ip,vc});WireContext c;
        if(it!=wire_contexts_.end())c=it->second;
        for(const auto& f:input_module_.input(ip,vc)){
            if(isHeader(f.type()))c=WireProtocol::get().decode(f);
            require(WireProtocol::matches(c,f),"drain inspection missing local VC header context");
            if(c.header.auxiliary)return true;
        }
    }
    return false;
}
void AuxGraphRouter::flit_traversal(long p) {
    if(p!=physic_ports_) {sim_router_template::flit_traversal(p);return;}
    if(output_module_.outbuffers(p).empty())return;
    flit_template f=output_module_.get_flit(p);
    output_module_.remove_flit(p);output_module_.remove_add(p);
    AuxBridge::get().transmit(address_.front(),p,mess_queue::m_pointer().current_time(),f);
}

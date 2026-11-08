#include "router_stalls.h"
#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <stdexcept>
#include <iomanip>
RouterStalls&RouterStalls::get(){static RouterStalls r;return r;}
RouterStalls::RouterStalls(){const char*p=std::getenv("NOC_ROUTER_STALL_LOG");if(p&&*p){enabled_=true;base_=p;}}
std::vector<RouterStalls::Probe> RouterStalls::before(sim_router_template&r,VC_state_type stage){
    std::vector<Probe> out;if(!enabled_)return out;
    auto&input=r.input_module();
    for(long p=0;p<r.physic_ports();++p)for(long v=0;v<r.vc_number();++v)
        if(input.state(p,v)==stage&&!input.input(p,v).empty()){
            const auto&f=input.input(p,v).front();out.push_back({p,v,f.getPacketId(),f.sequence(),input.input(p,v).size()});
        }
    return out;
}
void RouterStalls::after(long node,sim_router_template&r,VC_state_type stage,const std::vector<Probe>&before){
    if(!enabled_)return;auto&input=r.input_module();
    for(const auto&p:before){
        auto&c=counters_[{node,p.port,p.vc,int(stage)}];++c.eligible;c.max_queue=std::max<std::uint64_t>(c.max_queue,p.queued);
        bool same=!input.input(p.port,p.vc).empty()&&input.input(p.port,p.vc).front().getPacketId()==p.packet&&
            input.input(p.port,p.vc).front().sequence()==p.sequence;
        bool blocked=same&&input.state(p.port,p.vc)==stage;
        if(blocked){++c.blocked;++packet_blocked_[{p.packet,int(stage)}];}else ++c.granted;
    }
}
void RouterStalls::finish(){
    if(!enabled_)return;
    std::ofstream out(base_+".csv"),packets(base_+"_packets.csv");
    if(!out||!packets)throw std::runtime_error("cannot write NoC stall observation");
    out<<"node,input_port,vc,native_stage,eligible_slots,blocked_slots,progress_slots,maximum_observed_queue_flits\n";
    for(const auto&[key,c]:counters_){
        if(c.blocked+c.granted!=c.eligible)throw std::runtime_error("NoC stall counter conservation failed");
        auto[n,p,v,s]=key;out<<n<<','<<p<<','<<v<<','<<s<<','<<c.eligible<<','<<c.blocked<<','<<c.granted<<','<<c.max_queue<<'\n';
    }
    packets<<"packet,native_stage,blocked_head_flit_slots\n";
    for(const auto&[key,count]:packet_blocked_)packets<<key.first<<','<<key.second<<','<<count<<'\n';
    std::ofstream forwards(base_+"_forwarded.csv");
    if(!forwards)throw std::runtime_error("cannot write actual router forward counts");
    forwards<<"node,input_port,output_port,forwarded_flits\n";
    for(const auto&[key,count]:forwarded_){auto[n,i,o]=key;forwards<<n<<','<<i<<','<<o<<','<<count<<'\n';}
    std::ofstream by_packet(base_+"_packet_forwarded.csv"),busy(base_+"_forward_busy.csv");
    if(!by_packet||!busy)throw std::runtime_error("cannot write per-packet read-only NoC observations");
    by_packet<<"packet,node,input_port,output_port,forwarded_flits\n";
    for(const auto&[key,count]:packet_forwarded_){auto[p,n,i,o]=key;by_packet<<p<<','<<n<<','<<i<<','<<o<<','<<count<<'\n';}
    busy<<"node,begin,end\n"<<std::setprecision(17);
    for(const auto&[node,spans]:forward_busy_)for(auto[a,b]:spans)busy<<node<<','<<a<<','<<b<<'\n';
}
void RouterStalls::forward(long node,long input,long output,std::uint64_t packet,time_type time){
    if(!enabled_)return;
    ++forwarded_[{node,input,output}];++packet_forwarded_[{packet,node,input,output}];
    // Target router period is exactly one global cycle. This is observed
    // crossbar transfer occupancy, not inferred link capacity or queue time.
    auto& spans=forward_busy_[node];
    if(spans.empty()||time>spans.back().second)spans.push_back({time,time+1});
    else {
        if(time<spans.back().first)throw std::runtime_error("nonmonotonic router observer time");
        spans.back().second=std::max(spans.back().second,time+1);
    }
}
void RouterStalls::skip_blocked(long node,sim_router_template&r,std::uint64_t cycles){
    if(!enabled_)return;
    for(auto stage:{ROUTING_,VC_AB_,SW_AB_,HOME_})for(const auto&p:before(r,stage)){
        auto& c=counters_[{node,p.port,p.vc,int(stage)}];
        c.eligible+=cycles;c.blocked+=cycles;c.max_queue=std::max<std::uint64_t>(c.max_queue,p.queued);
        packet_blocked_[{p.packet,int(stage)}]+=cycles;
    }
}

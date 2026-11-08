#pragma once
#include "../sim_router.h"
#include <map>
#include <tuple>
#include <vector>
#include <cstdint>
#include <string>

// Read-only diagnostic. Does not add events, make decisions, or read RNG.
class RouterStalls {
    struct Probe {long port,vc;std::uint64_t packet;long sequence;std::size_t queued;};
    struct Count {std::uint64_t eligible=0,blocked=0,granted=0,max_queue=0;};
    bool enabled_=false;std::string base_;
    std::map<std::tuple<long,long,long,int>,Count> counters_;
    std::map<std::pair<std::uint64_t,int>,std::uint64_t> packet_blocked_;
    std::map<std::tuple<long,long,long>,std::uint64_t> forwarded_;
    std::map<std::tuple<std::uint64_t,long,long,long>,std::uint64_t> packet_forwarded_;
    std::map<long,std::vector<std::pair<time_type,time_type>>> forward_busy_;
    RouterStalls();
public:
    static RouterStalls& get();
    bool enabled()const{return enabled_;}
    std::vector<Probe> before(sim_router_template&,VC_state_type);
    void after(long,sim_router_template&,VC_state_type,const std::vector<Probe>&);
    void forward(long,long,long,std::uint64_t,time_type);
    void skip_blocked(long,sim_router_template&,std::uint64_t);
    void finish();
};

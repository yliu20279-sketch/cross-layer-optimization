#pragma once
#include <map>
#include <vector>
#include <tuple>
#include <cstdint>
#include <deque>
#include <memory>
#include <fstream>
#include "ramulator2_wrapper.h"
// Numerical waveform guidance from explicit blocking program waits. No new
// hardware, latency estimate, timestamp-inferred predecessor, or barrier.
class ProgramFences {
    struct Service {long offset,bytes,predicted;};
    struct Fence {long parent=0,gap=0,predicted=0,actual=-1;std::uint64_t tx=0,rx=0;std::vector<Service> services;
        bool dram=false,write=false;std::uint64_t address=0,bytes=0,request=0;};
    struct Release {long fence,offset;};
    std::map<std::pair<long,long>,Fence> fences_;
    std::map<std::tuple<long,std::uint64_t,bool>,long> completed_;
    std::map<std::tuple<long,std::uint64_t,bool>,Release> releases_;
    std::map<std::pair<long,long>,long> services_;
    bool enabled_=false,command_clock_=false;
    bool dram_enabled_=false;
    std::unique_ptr<memory::Ramulator2Wrapper> dram_[16];
    std::map<std::pair<long,long>,std::vector<long>> children_;
    std::map<std::tuple<long,std::uint64_t,bool>,std::vector<long>> waiters_;
    std::deque<std::pair<long,long>> pending_;
    std::ofstream dram_log_;
    long dram_count_=0,dram_changed_=0,wait_count_=0;
    void resolve_memory();
    long deferred_=0,moved_=0,total_=0;
    ProgramFences();
    void resolve();
public:
    static ProgramFences&get();
    bool enabled()const{return enabled_;}
    bool command_clock()const{return command_clock_;}
    long issue_time(long n,std::uint64_t id,bool send,long fallback)const;
    bool busy(long n,long t)const;
    bool eligible(long n,std::uint64_t id,bool send,long now);
    void complete(long n,std::uint64_t id,bool send,long now);
    void finish();
};

#pragma once
#include "../index.h"
#include <cstdint>
#include <fstream>
#include <map>
#include <utility>
#include <array>
#include <vector>

class ReceiveContract {
    struct Post {long source;time_type ready;std::uint64_t bytes,address,written=0;bool header=false,done=false;std::uint64_t metadata=0;};
    bool enabled_=false;
    bool noc_first_=false;
    bool npu_first_=false;
    std::array<long,16> source_snapshot_edge_{};
    std::array<bool,16> source_snapshot_busy_{};
    std::map<std::pair<long,std::uint64_t>,Post> posts_;
    std::map<std::pair<long,long>,long> local_;
    // Arbitration examines only the CURRENT edge. Past source/receive uses
    // remain in the unchanged audit logs; retaining millions of historical
    // map entries is unnecessary for the physical event simulation.
    struct NISlot {long time=-1,source=0,writes=0;};
    mutable std::array<NISlot,16> ni_{};
    NISlot& current(long,long)const;
    long local_bytes(long,long)const;
    std::ofstream log_;
    long waits_post_=0,waits_sram_=0,finished_=0,source_overbook_=0;
    ReceiveContract();
    static long edge(time_type);
public:
    struct PostedView {long destination,source;std::uint64_t id,bytes,address,metadata;time_type ready;};
    std::vector<PostedView> posted_views()const;
    bool protocol_sram(long,time_type,std::uint64_t,const char*);
    static ReceiveContract&get();
    bool enabled()const{return enabled_;}
    bool skip_compatible()const{return enabled_&&noc_first_;}
    time_type post_time(long,std::uint64_t)const;
    void skip_post_waits(std::uint64_t count){waits_post_+=count;}
    void source_snapshot(long,time_type,bool);
    bool source_can_read(long,time_type)const;
    void source_read(long,time_type);
    bool ready(long,std::uint64_t,long,time_type,bool,long);
    void retire(long,std::uint64_t,long,time_type,bool,long,bool);
    void finish();
};

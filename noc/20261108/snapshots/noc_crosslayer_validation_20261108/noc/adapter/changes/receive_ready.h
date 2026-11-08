#pragma once
#include "../sim_router.h"
#include "receive_contract.h"
#include <array>
#include <deque>
#include <fstream>
#include <map>
#include <vector>

// Receiver-ready rendezvous. Trace READ events are releases of software
// descriptors; a sender is gated only by a real returned wire notification.
class ReceiveReady {
    static constexpr unsigned SLOTS=4096, INBOX=8;
    static constexpr std::uint64_t BASE=4194304-SLOTS*32;
    struct Grant {std::uint64_t id=0,bytes=0;long peer=-1;int state=0;};
    struct Notice {std::uint64_t id,bytes;long peer;time_type eligible;unsigned slot,probes=0;bool write=false;};
    struct Lookup {std::uint64_t id=0;unsigned slot=0,probes=0;int state=0;time_type eligible=0;};
    bool enabled_=false,started_=false;
    std::array<sim_router_template*,16> routers_{};
    std::array<std::vector<ReceiveContract::PostedView>,16> posts_;
    std::array<std::size_t,16> next_{};
    std::array<bool,16> descriptor_read_{};
    std::array<std::array<Grant,SLOTS>,16> table_{};
    std::array<std::deque<Notice>,16> inbox_;
    std::array<Lookup,16> lookup_{};
    std::array<unsigned,16> occupied_{};
    std::array<unsigned,16> initialized_{};
    // These maps are audit-only; they do not route packets or grant service.
    std::map<std::uint64_t,int> emitted_,accepted_,admitted_;
    std::ofstream log_;
    std::size_t packet_id_=(std::size_t(1)<<61);
    long total_=0,issued_=0,received_=0,released_=0,max_inbox_=0,max_entries_=0;
    static unsigned hash(std::uint64_t);
    bool source_pending(long)const;
    bool memory(long,time_type,unsigned,const char*);
    void record(time_type,const char*,long,std::uint64_t,long=0);
public:
    static ReceiveReady&get();
    ReceiveReady();
    bool enabled()const{return enabled_;}
    bool needs_progress()const{return enabled_&&released_<total_;}
    bool idle_until(time_type,time_type&)const;
    void register_router(long,sim_router_template*);
    void start();
    void tick(long,time_type);
    bool admit(std::size_t,long,long,time_type);
    static bool is_notice(const flit_template&);
    bool can_accept(long)const;
    bool consume(long,time_type,const flit_template&);
    void forward(long,long,long,long,long,const flit_template&,time_type);
    void finish();
};

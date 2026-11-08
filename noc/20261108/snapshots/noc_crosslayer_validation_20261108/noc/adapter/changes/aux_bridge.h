#ifndef AUX_BRIDGE_H
#define AUX_BRIDGE_H
#include "../sim_router.h"
#include "../mess_event.h"
#include "wire_protocol.h"
#include <array>
#include <deque>
#include <fstream>
#include <map>
#include <tuple>

// Implementation of the already-defined nine-CS, one-AUX-per-node datapath.
// The initial configuration and timing are explicit test inputs, not a policy.
class AuxBridge {
    friend class DynamicControl;
    struct Route {long source,destination,gateway;};
    struct Token {flit_template flit;long gateway;time_type eligible;std::uint64_t message_id=0;};
    using Key=std::tuple<size_t,long,long,time_type>;
    struct Expected {Data_type data;flit_type type;long ordinal;};
    // Observer-only metadata. Not a modeled hardware FIFO or control input.
    struct CreditTrace {size_t packet;long source,destination,ordinal;};
    std::array<std::deque<CreditTrace>,16> credit_trace_;
    bool enabled_=false,tick_pending_=false;
    int depth_=0;
    time_type segment_delay_=0,switch_delay_=0,credit_delay_=0,ni_period_=0;
    std::array<int,9> cs_{};
    std::array<int,16> tx_{},rx_{},connection_{};
    std::array<sim_router_template*,16> routers_{};
    std::array<std::deque<Token>,16> mesh_fifo_,aux_fifo_;
    std::array<time_type,16> hold_until_{},last_mesh_enqueue_{};
    std::array<bool,16> prefer_aux_{};
    std::array<bool,16> write_locked_{},held_aux_{};
    std::array<long,16> inflight_{},queued_{},pending_credit_{};
    std::array<WireContext,16> wire_tx_{},wire_rx_{};
    std::array<WireContext,16> aux_arrival_context_{};
    std::map<size_t,Route> routes_;
    std::map<Key,std::deque<Expected>> expected_;
    std::ofstream log_;
    long injected_=0,written_=0,control_retired_=0,aux_sent_=0,aux_written_=0,mesh_written_=0;
    long credits_=0,ni_waits_=0,mesh_backpressure_=0,shared_contention_=0;
    long max_aux_depth_=0,max_mesh_depth_=0,completed_=0;
    long held_selection_checks_=0,selection_changes_prevented_=0;
    long header_retired_=0,payload_written_=0;
    AuxBridge();
    static Key key(const flit_template&);
    static long ordinal(const flit_template&);
    void request_service(time_type);
    time_type eligible_after(time_type) const;
    void event(time_type,const char*,long,const flit_template&,long);
    void validate_connections();
    void check_credit_balance() const;
public:
    static AuxBridge&get();
    bool enabled() const {return enabled_;}
    int depth() const {return depth_;}
    bool mesh_full(long n)const{return mesh_fifo_.at(n).size()>=size_t(depth_);}
    bool quiescent_until(time_type,time_type&)const;
    bool completely_idle()const;
    void skip_quiescent(std::uint64_t);
    bool uses_aux(const flit_template&) const;
    long gateway(const flit_template&) const;
    bool source_route(const flit_template&,long&) const;
    void register_router(long,sim_router_template*);
    void observe_injection(const flit_template&);
    bool mesh_ready(long,time_type,bool control=false);
    void enqueue_mesh(long,time_type,const flit_template&,std::uint64_t=0);
    void transmit(long,long,time_type,const flit_template&);
    void arrive(const mess_event&);
    void service(time_type);
    void credit_received(long,long,long);
    void observe_credit_reservation(long,const flit_template&,long);
    void finish();
};

class AuxGraphRouter:public CGraphTopo {
    mutable std::map<std::pair<long,long>,WireContext> wire_contexts_;
    const WireContext& wire_context(long,long,const flit_template&) const;
protected:
    add_type routing_destination(const flit_template&,long,long) const override;
    bool local_destination(const flit_template&,long,long) const override;
    bool local_receive_ready(time_type,const flit_template&) override;
    void deliver_local(time_type,const flit_template&) override;
    void deliver_local_context(time_type,const flit_template&,long,long) override;
    void observe_injection(const flit_template&) override;
    void routingAlg(const add_type&,const add_type&,long,long) override;
public:
    AuxGraphRouter(long,long,long,long,const add_type&,long,long);
    void flit_traversal(long) override;
    bool contains_aux_input();
    bool cached_stalled_local_header(long,long)const override;
};
#endif

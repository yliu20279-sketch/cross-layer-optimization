#ifndef NOC_DYNAMIC_CONTROL_H
#define NOC_DYNAMIC_CONTROL_H
#include "../flit.h"
#include <array>
#include <map>
#include <fstream>
#include <cstdint>

class DynamicControl {
    struct Pending {int state=0,epoch=0;bool valid=false,committed=false;};
    struct Agent {
        std::array<Pending,3> pending;
        uint64_t accepted=0,written=0;
        int epoch=0,armed_epoch=-1;
        bool frozen=false,permit=false;
    };
    struct Object {int node,kind,target,state;};
    struct Command {int type=7,node=0,op=0,kind=0,target=0,epoch=0,state=0;};
    struct Frame {Command command;Data_type data;};
    enum Stage {WAIT_READY=-1,LOAD,FREEZE,COUNT,CREDIT,PERMIT,COMMIT,ARM,RUN,DONE};
    bool enabled_=false,waiting_=false,started_=false,finished_=false;
    bool bad_load_=false,bad_sent_=false,expect_bad_=false;
    bool stale_probe_=false,duplicate_arm_probe_=false,duplicate_arm_pending_=false;
    bool duplicate_arm_checked_=false;
    bool application_gate_=false,phase_tick_started_=false;
    int drop_ready_node_=-1,drop_ready_chunk_=-1,duplicate_ready_node_=-1,duplicate_ready_chunk_=-1;
    std::array<time_type,16> gate_time_{},source_resume_{};
    std::array<std::array<uint32_t,16>,16> source_demand_{},received_demand_{};
    std::array<unsigned,16> received_chunks_{};
    long notifications_=0,duplicate_notifications_=0;
    uint64_t duplicate_arm_accepted_=0;
    int next_epoch_=1,index_=0;
    Stage stage_=LOAD;
    time_type start_=20,timeout_=20000,stage_start_=0;
    std::array<Agent,16> agents_;
    std::array<int,9> next_cs_{};
    std::array<int,16> next_tx_{},next_rx_{};
    std::vector<Object> objects_;
    std::map<size_t,int> packet_epoch_;
    std::map<size_t,Frame> frames_;
    size_t next_id_=(size_t(1)<<62);
    Command expected_;
    uint64_t sum_a_=0,sum_w_=0;
    long requests_=0,responses_=0,rejected_=0,ignored_=0,count_rounds_=0,credit_rounds_=0;
    std::ofstream log_;
    DynamicControl();
    void emit(int source,const Command&,uint64_t=0,uint64_t=0,uint64_t=0);
    void request(const Command&);
    void receive_request(long,const Command&);
    void receive_response(long,const Command&,const Data_type&);
    void set_stage(Stage);
    bool local_drained(int) const;
    bool legal_state(int,int,int) const;
    void record(const char*,int=-1,uint64_t=0,uint64_t=0);
    void summary(bool,const char*);
    void receive_phase_ready(long,const Command&,const Data_type&);
    void phase_summary() const;
public:
    static DynamicControl&get();
    bool enabled() const {return enabled_;}
    bool needs_router_progress() const {return enabled_&&started_&&!finished_;}
    bool is_control(const flit_template&) const;
    bool admit_trace(size_t,long,long) const;
    int active_epoch(long node) const {return agents_.at(node).epoch;}
    void rewrite(flit_template&);
    void observe(const flit_template&,bool serialized_aux=false,int serialized_epoch=0);
    void aux_written(const flit_template&,int serialized_epoch=0);
    bool consume(long,const flit_template&);
    void start();
    void tick(time_type);
    void finish();
    void phase_ready(long);
    void account_source_wait(flit_template&);
};
#endif

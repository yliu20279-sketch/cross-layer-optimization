// Persistent Ramulator2 + PopNet, driven by completion dependencies.
// NPU scheduler quantum: 1 ns. DRAM retains 1.25 ns ticks; NoC wire events
// retain their fractional times. DeepStack supplies full-byte Bank service.
#include <ramulator/base/config.h>
#include <ramulator/base/factory.h>
#include <ramulator/base/request.h>
#include <ramulator/frontend/i_frontend.h>
#include <ramulator/memory_system/i_memory_system.h>
#include "configuration.h"
#include "sim_foundation.h"
#include "mess_queue.h"
#include "micro_stats.h"
#include "SRGen.h"
#include <array>
#include <deque>
#include <fstream>
#include <iomanip>
#include <memory>
#include <queue>
#include <sstream>
#include <stdexcept>
#include <unordered_map>
#include <functional>
#include <algorithm>

static std::function<void(size_t,double)> packet_callback;
void coupled_packet_complete(size_t id,double t) { if(!packet_callback) throw std::runtime_error("missing packet callback");packet_callback(id,t); }
static std::string envs(const char* key,const char* def="") { const char* p=std::getenv(key);return p?p:def; }
static double envd(const char* key,const char* def) { return std::stod(envs(key,def)); }
static std::vector<std::string> split(const std::string&s){std::vector<std::string>v;std::stringstream q(s);std::string x;while(std::getline(q,x,','))v.push_back(x);return v;}
static uint64_t mix64(uint64_t x){x+=0x9e3779b97f4a7c15ULL;x=(x^(x>>30))*0xbf58476d1ce4e5b9ULL;x=(x^(x>>27))*0x94d049bb133111ebULL;return x^(x>>31);}
static int decode_bank_field(uint64_t address,int shift){uint64_t field=(address>>shift)&0xfULL;return int(((field&3ULL)<<2)|((field>>2)&3ULL));}
static int decode_layer(const std::string& task){
    auto p=task.find('L');if(p==std::string::npos)return -1;++p;
    auto q=p;while(q<task.size()&&task[q]>='0'&&task[q]<='9')++q;
    return q==p?-1:std::stoi(task.substr(p,q-p));
}
static uint64_t encode_bank_field(uint64_t address,int shift,int decoded){uint64_t field=uint64_t((decoded>>2)|((decoded&3)<<2));return (address&~(0xfULL<<shift))|(field<<shift);}
static uint64_t map_bank_address(uint64_t address,int op_id,uint64_t tx_index,const std::string&mode,int effective_banks,int shift){
    if(mode=="native")return address;
    int target=0;
    if(mode=="alias")target=decode_bank_field(address,shift)%effective_banks;
    else if(mode=="soft_hot"||mode=="soft_hot_xor")return address;
    else if(mode=="balanced")target=int(mix64((uint64_t(uint32_t(op_id))<<32)^tx_index)%16ULL);
    else throw std::runtime_error("HB_BANK_ADDRESS_MODE must be native, alias, soft_hot, soft_hot_xor, or balanced");
    return encode_bank_field(address,shift,target);
}
#include "runtime_extensions.h"
struct Op {
    int id,pe,src,dst,rank,owner=-1;std::string kind,task,phase,scope;
    uint64_t bytes,sample,address,cycles,next=0,expected=0,received=0,outstanding=0;
    int state=0,degree=0;std::vector<int> children;
    double ready=-1,start=-1,gate=-1,backend=-1,done=-1,first=-1;
    double memory_service_start=-1,ideal_bank_cycles=0,bank_penalty_cycles=0;
    uint64_t packets=0;bool held=false;
};
struct Event {double time;int type,id;size_t packet;int flits;bool operator>(const Event&b)const{return std::tie(time,type,id,packet)>std::tie(b.time,b.type,b.id,b.packet);} };
struct BankAggregate {
    uint64_t transactions=0,transactions_with_wait=0,wait_events=0,row_status_0=0,row_status_1=0,row_status_other=0;
    double represented_bytes=0,queue_ticks=0,cross_request_wait_ticks=0,row_command_ticks=0,completion_ticks=0;
};

int main(int argc,char**argv) {try{
    const std::string graph=envs("HB_GRAPH"),out=envs("HB_OUT"),ramcfg=envs("HB_RAM_CONFIG");
    if(graph.empty()||out.empty()||ramcfg.empty())throw std::runtime_error("HB_GRAPH, HB_OUT, HB_RAM_CONFIG required");
    const double dm=envd("HB_DRAM_MULT","1"),nm=envd("HB_NOC_MULT","1"),scale=envd("HB_NOC_SCALE","1024"),memhold=envd("HB_MEM_HOLD","0"),nethold=envd("HB_NET_HOLD","0"),switch_cost=envd("HB_SWITCH_COST","0");
    const double base_mem_bytes_per_cycle=envd("HB_BASE_BYTES_PER_CYCLE","102.4");
    const double pci_rate=envd("HB_PCIE_GBPS","55.04"),pci_latency=envd("HB_PCIE_LATENCY_NS","270");
    const double progress_watchdog=envd("HB_PROGRESS_WATCHDOG_CYCLES","10000000");
    if(pci_rate<=0||pci_latency<0)throw std::runtime_error("invalid PCIe budget");
    const int architecture_tx_bytes=int(envd("HB_ARCH_TX_BYTES","256"));
    const uint64_t max_outstanding_per_op=uint64_t(envd("HB_MAX_OUTSTANDING_PER_OP","1000000000"));
    const bool bank_detail=envd("HB_BANK_LOG_DETAIL","1")!=0;
    const std::string bank_address_mode=envs("HB_BANK_ADDRESS_MODE","native");
    const int effective_banks=int(envd("HB_EFFECTIVE_BANKS","16")),bank_field_shift=int(envd("HB_BANK_FIELD_SHIFT","14"));
    if(dm<=0||nm<=0||scale<1||memhold<0||nethold<0||max_outstanding_per_op<1)throw std::runtime_error("invalid control");
    if(bank_address_mode!="native"&&bank_address_mode!="alias"&&bank_address_mode!="soft_hot"&&bank_address_mode!="soft_hot_xor"&&bank_address_mode!="balanced")throw std::runtime_error("invalid HB_BANK_ADDRESS_MODE");
    if(effective_banks!=2&&effective_banks!=4&&effective_banks!=8&&effective_banks!=16)throw std::runtime_error("HB_EFFECTIVE_BANKS must be 2,4,8,16");
    if(bank_field_shift<0||bank_field_shift>59)throw std::runtime_error("invalid HB_BANK_FIELD_SHIFT");
    SRGen rng;configuration config(argc,argv);mess_queue network_queue(0);sim_foundation network;
    const double flitbytes=config.flit_size()*8.;if(flitbytes!=32*nm)throw std::runtime_error("NoC width mismatch");
    std::array<Ramulator::IFrontEnd*,16> fronts;std::array<Ramulator::IMemorySystem*,16> memories;
    int tx=0;double tck=0;
    for(int ch=0;ch<16;++ch){auto cfg=Ramulator::Config::parse_config_file(ramcfg);fronts[ch]=Ramulator::Factory::create_frontend(cfg);memories[ch]=Ramulator::Factory::create_memory_system(cfg);fronts[ch]->connect_memory_system(memories[ch]);memories[ch]->connect_frontend(fronts[ch]);tx=memories[ch]->get_tx_bytes();tck=memories[ch]->get_tCK();}
    if(std::abs(tck-1.25)>1e-9||architecture_tx_bytes<=0||base_mem_bytes_per_cycle<=0||tx!=int(architecture_tx_bytes*dm))throw std::runtime_error("DRAM budget/config mismatch");
    std::vector<Op> ops;std::ifstream in(graph+"/ops.csv");std::string line;std::getline(in,line);
    while(std::getline(in,line)){auto v=split(line);if(v.size()!=13&&v.size()!=14)throw std::runtime_error("bad ops schema");Op o;o.id=std::stoi(v[0]);o.kind=v[1];o.task=v[2];o.phase=v[3];o.pe=std::stoi(v[4]);o.bytes=std::stoull(v[5]);o.sample=std::stoull(v[6]);o.address=std::stoull(v[7]);o.cycles=std::stoull(v[8]);o.src=std::stoi(v[9]);o.dst=std::stoi(v[10]);o.scope=v[11];o.rank=std::stoi(v[12]);if(v.size()==14)o.owner=std::stoi(v[13]);if(o.id!=int(ops.size()))throw std::runtime_error("non-dense IDs");ops.push_back(o);}
    std::unordered_map<int,double> deepstack_actual,deepstack_ideal,deepstack_penalty;const std::string deepstack_timing=envs("HB_DEEPSTACK_TIMING");
    if(!deepstack_timing.empty()){std::ifstream ds(deepstack_timing);if(!ds)throw std::runtime_error("cannot open HB_DEEPSTACK_TIMING");std::getline(ds,line);
        while(std::getline(ds,line)){auto v=split(line);if(v.size()!=4)throw std::runtime_error("bad DeepStack timing v2 schema");int id=std::stoi(v[0]);double actual=std::stod(v[1]),ideal=std::stod(v[2]),penalty=std::stod(v[3]);if(actual<0||ideal<0||penalty<0||std::abs(actual-ideal-penalty)>1e-8||!deepstack_actual.emplace(id,actual).second)throw std::runtime_error("bad/duplicate DeepStack timing");deepstack_ideal.emplace(id,ideal);deepstack_penalty.emplace(id,penalty);}
        for(auto&o:ops)if((o.kind=="LOAD"||o.kind=="STORE")&&!deepstack_actual.count(o.id))throw std::runtime_error("missing DeepStack memory-op timing");}
    std::ifstream depin(graph+"/deps.csv");std::getline(depin,line);uint64_t edgecount=0;
    while(std::getline(depin,line)){auto v=split(line);int s=std::stoi(v[0]),d=std::stoi(v[1]);ops.at(s).children.push_back(d);ops.at(d).degree++;edgecount++;}
    if(ops.empty())throw std::runtime_error("empty graph");
    std::unordered_map<int,double> owner_release;
    const std::string release_path=envs("HB_REQUEST_RELEASES");
    if(!release_path.empty()){
        std::ifstream release_in(release_path);if(!release_in)throw std::runtime_error("cannot open HB_REQUEST_RELEASES");
        std::getline(release_in,line);
        while(std::getline(release_in,line)){
            auto v=split(line);if(v.size()<2)throw std::runtime_error("bad request release schema");
            int owner=std::stoi(v[0]);double cycle=std::stod(v[1]);
            if(owner<0||cycle<0||!owner_release.emplace(owner,cycle).second)throw std::runtime_error("bad/duplicate request release");
        }
    }
    std::map<std::string,std::array<double,2>> modes;std::ifstream mi(graph+"/modes.csv");std::getline(mi,line);
    while(std::getline(mi,line)){auto v=split(line);modes[v[0]]={std::stod(v[1])*nm,std::stod(v[2])*nm};}
    if(modes.size()!=4)throw std::runtime_error("four modes required");
    for(auto&m:modes)if(std::abs(m.second[0]+m.second[1]-1536*nm)>1e-7)throw std::runtime_error("mode width budget mismatch");
    std::ofstream log(out+"/events.csv"),packlog(out+"/packet_completions.csv"),modelog(out+"/mode_changes.csv");
    log<<"id,task,phase,kind,pe,rank,inference_request_id,bytes,sample_bytes,ready,start,memory_service_start,ideal_bank_cycles,bank_penalty_cycles,backend_done,modeled_gate,done\n";
    packlog<<"packet_id,op_id,inject,arrive\n";modelog<<"cycle,mode,local_pending_bytes,global_pending_bytes,drain_complete,switch_ready\n";
    log<<std::setprecision(17);packlog<<std::setprecision(17);modelog<<std::setprecision(17);
    ThermalLoop thermal(out);
    const std::string fixed_mode=envs("HB_FIXED_MODE");
    if(!fixed_mode.empty()&&!modes.count(fixed_mode))throw std::runtime_error("unknown fixed mode");
    const double bsa_share=envd("HB_BSA_SHARE","0.5");
    const bool hic_serial=envd("HB_HIC_SERIAL","0")!=0;
    if(bsa_share<=0||bsa_share>=1||switch_cost<0)throw std::runtime_error("invalid engine/switch control");
    std::ofstream banklog(out+"/bank_requests.csv"),complog(out+"/compute_resources.csv");
    banklog<<"op_id,transaction_id,inference_request_id,partition,address,request_bytes,represented_bytes,submit_cycle,callback_cycle,controller_arrive_tick,first_issue_tick,final_issue_tick,controller_depart_tick,controller_queue_ticks,cross_request_bank_wait_ticks,cross_request_bank_wait_events,row_command_ticks,completion_ticks,row_status,channel,rank,bankgroup,bank,row,column,type\n"<<std::setprecision(17);
    complog<<"op_id,npu,engine,share,frequency,ready,start,done,base_cycles\n"<<std::setprecision(17);
    std::deque<int> ready,netwait;std::array<std::vector<int>,16> memwait;
    std::array<double,32> cpufree{};std::array<double,16> membus{},srcfree{},dstfree{};std::array<double,2> poolfree{};double epfree=0,now=0;
    std::array<double,2> pci_free{};std::array<double,64> dma_credit_free{};
    std::ofstream dmalog(out+"/dma_resources.csv");
    dmalog<<"op_id,direction,credit,bytes,ready,start,service_cycles,fixed_latency_cycles,done\n"<<std::setprecision(17);
    uint64_t completed=0,packet_id=0,dram_request_id=0,dram_outstanding=0,packets_done=0,inflight=0,active_net=0,membytes=0,sampledbytes=0,netbytes=0,flits_sent=0,event_jump_cycles=0,event_jump_count=0;
    std::map<std::tuple<int,int,int>,BankAggregate> bank_aggregates;std::array<uint64_t,256> bank_mapping_counts{};
    std::map<std::pair<int,int>,double> layer_bank_wait_ticks;
    double memory_tick=tck,totalcycle=0,switch_ready=0,last_progress=0;long mode_epoch=-1;std::string mode;bool mem_fault_used=false,net_fault_used=false;
    std::unordered_map<size_t,std::pair<int,double>> packets;
    std::priority_queue<Event,std::vector<Event>,std::greater<Event>> events;
    std::function<void(int)> finish;
    auto check=[&](int id){Op&o=ops[id];if(o.state!=2)return;if(o.kind=="LOAD"||o.kind=="STORE"){if(o.received!=o.expected||o.backend<0)return;}else if(o.kind=="NET"){if(o.packets)return;}if(now+1e-8<o.gate)return;finish(id);};
    finish=[&](int id){Op&o=ops[id];if(o.state==3)throw std::runtime_error("duplicate completion");o.state=3;o.done=now;completed++;last_progress=now;totalcycle=std::max(totalcycle,now);if(o.kind=="NET"&&o.src!=o.dst&&o.bytes)active_net--;
        log<<id<<','<<o.task<<','<<o.phase<<','<<o.kind<<','<<o.pe<<','<<o.rank<<','<<o.owner<<','<<o.bytes<<','<<o.sample<<','<<o.ready<<','<<o.start<<','<<o.memory_service_start<<','<<o.ideal_bank_cycles<<','<<o.bank_penalty_cycles<<','<<o.backend<<','<<o.gate<<','<<o.done<<'\n';
        for(int d:o.children){Op&x=ops[d];if(--x.degree<0)throw std::runtime_error("negative indegree");x.ready=std::max(x.ready,now);if(!x.degree)ready.push_back(d);}
    };
    packet_callback=[&](size_t pid,double time){auto it=packets.find(pid);if(it==packets.end())throw std::runtime_error("unknown/double packet completion");int id=it->second.first;Op&o=ops[id];packlog<<pid<<','<<id<<','<<it->second.second<<','<<time<<'\n';o.backend=std::max(o.backend,time);o.packets--;packets_done++;inflight--;packets.erase(it);
        if(!o.packets){if(!net_fault_used&&nethold){net_fault_used=true;o.gate=std::max(o.gate,now+nethold);events.push({o.gate,0,id,0,0});}check(id);}
    };
    for(auto&o:ops)if(!o.degree){
        double release=0;
        if(o.owner>=0&&!release_path.empty()){
            auto it=owner_release.find(o.owner);if(it==owner_release.end())throw std::runtime_error("missing request release owner");
            release=it->second;
        }
        o.ready=release;
        if(release<=0)ready.push_back(o.id);else events.push({release,3,o.id,0,0});
    }
    while(completed<ops.size()){
        if(now>1000000000.)throw std::runtime_error("coupled watchdog");
        if(progress_watchdog>0&&now-last_progress>progress_watchdog)throw std::runtime_error("no-progress watchdog");
        // Backends execute before newly ready operations can submit at this time.
        if(thermal.enabled&&now>0&&uint64_t(now)%100000==0)thermal.step(now);
        network_queue.coupled_advance(now);
        while(memory_tick<=now+1e-8){for(int ch=0;ch<16;++ch)memories[ch]->tick();memory_tick+=tck;}
        bool work=true;
        while(work){work=false;
            while(!events.empty()&&events.top().time<=now+1e-8){Event e=events.top();events.pop();Op&o=ops[e.id];work=true;
                if(e.type==3){ready.push_back(e.id);}
                else if(e.type==0){check(e.id);}
                else if(e.type==1){o.state=2;o.next=0;o.expected=o.sample?(o.sample+tx-1)/tx:0;memwait[o.pe].push_back(o.id);if(!o.sample){o.backend=now;check(o.id);}}
                else if(e.type==2){add_type s={o.src%4,o.src/4},d={o.dst%4,o.dst/4};packets[e.packet]={o.id,now};inflight++;flits_sent+=e.flits;SPacket p;p.startTime=now;p.sourceAddress=s;p.destinationAddress=d;p.packetSize=e.flits;p.id=e.packet;network.router(s).inputTrace(p);network.router(s).receive_packet();}
            }
            while(!ready.empty()){int id=ready.front();ready.pop_front();Op&o=ops[id];if(o.state)throw std::runtime_error("duplicate dispatch");work=true;o.state=1;
                if(o.kind=="BARRIER"||o.kind=="CPU"){o.start=o.gate=o.backend=now;finish(id);}
                else if(o.kind=="DMA_H2D"||o.kind=="DMA_D2H"){
                    int direction=o.kind=="DMA_H2D"?0:1;
                    int credit=int(std::min_element(dma_credit_free.begin(),dma_credit_free.end())-dma_credit_free.begin());
                    o.start=std::max({now,pci_free[direction],dma_credit_free[credit]});
                    if(o.start>now){o.state=0;events.push({o.start,3,id,0,0});continue;}
                    double service=std::ceil(o.bytes/pci_rate);
                    pci_free[direction]=o.start+service;o.gate=o.backend=pci_free[direction]+pci_latency;
                    dma_credit_free[credit]=o.gate;o.state=2;
                    dmalog<<id<<','<<(direction?"D2H":"H2D")<<','<<credit<<','<<o.bytes<<','<<o.ready<<','<<o.start<<','<<service<<','<<pci_latency<<','<<o.gate<<'\n';
                    events.push({o.gate,0,id,0,0});
                }
                else if(o.kind=="COMPUTE"){bool partitioned=o.phase!="COMPUTE";int engine=o.phase=="COMPUTE_BGA"?1:0;
                    double share=partitioned?(engine?1-bsa_share:bsa_share):1.;int key=(!partitioned||hic_serial)?o.pe:o.pe+16*engine;
                    o.start=std::max(now,cpufree[key]);
                    // Latch DVFS at actual admission, not when queued in the future.
                    if(o.start>now){o.state=0;events.push({o.start,3,id,0,0});continue;}
                    double frequency=thermal.scale[o.pe];o.gate=o.start+std::ceil(o.cycles/(share*frequency));cpufree[key]=o.gate;o.backend=o.gate;
                    thermal.reserve(o.pe,o.start,o.gate,share,frequency,true);
                    complog<<id<<','<<o.pe<<','<<(partitioned?(engine?"BGA":"BSA"):"FULL")<<','<<share<<','<<frequency<<','<<o.ready<<','<<o.start<<','<<o.gate<<','<<o.cycles<<'\n';o.state=2;events.push({o.gate,0,id,0,0});}
                else if(o.kind=="LOAD"||o.kind=="STORE"){o.start=now;o.memory_service_start=std::max(now,membus[o.pe]);if(!deepstack_timing.empty()){o.ideal_bank_cycles=deepstack_ideal.at(o.id);o.bank_penalty_cycles=deepstack_penalty.at(o.id);o.gate=o.memory_service_start+deepstack_actual.at(o.id);}else{o.ideal_bank_cycles=std::ceil(o.bytes/(base_mem_bytes_per_cycle*dm));o.gate=o.memory_service_start+o.ideal_bank_cycles;}membus[o.pe]=o.gate;thermal.reserve(o.pe,o.start,o.gate,1.,1.,false,o.bytes);membytes+=o.bytes;sampledbytes+=o.sample;events.push({o.start,1,id,0,0});events.push({o.gate,0,id,0,0});}
                else if(o.kind=="NET"){if(o.src==o.dst||!o.bytes){o.start=o.gate=o.backend=now;finish(id);}else netwait.push_back(id);}
                else throw std::runtime_error("unknown operation");
            }
        }
        if(!netwait.empty()&&now>=switch_ready){
            uint64_t lb=0,gb=0;for(int id:netwait)(ops[id].scope=="local"?lb:gb)+=ops[id].bytes;
            // Dynamic execution keeps a non-zero reserve for both traffic
            // classes. FULL_* remains available only as an explicit fixed
            // control; selecting a zero-share mode from a transient queue
            // snapshot can violate liveness when the other class arrives.
            std::string wanted=double(lb)/(lb+gb)>=.6?"LOCAL_BIAS":"GLOBAL_BIAS";
            if(!fixed_mode.empty())wanted=fixed_mode;
            long epoch=long(now/100000);bool blocked=false;
            if(mode.empty()||epoch!=mode_epoch){if(wanted!=mode){if(active_net||inflight||network_queue.message_queue_size())blocked=true;else{switch_ready=now+(mode.empty()?0:switch_cost);mode=wanted;modelog<<now<<','<<mode<<','<<lb<<','<<gb<<','<<now<<','<<switch_ready<<'\n';}}if(!blocked)mode_epoch=epoch;}
            if(!blocked&&now>=switch_ready){while(!netwait.empty()){int id=netwait.front();netwait.pop_front();Op&o=ops[id];int scope=o.scope=="local"?0:1;double rate=modes.at(mode)[scope];o.start=std::max({now,poolfree[scope],srcfree[o.src],dstfree[o.dst],epfree});poolfree[scope]=o.start+std::ceil(o.bytes/rate);srcfree[o.src]=dstfree[o.dst]=o.start+std::ceil(o.bytes/(32*nm));epfree=o.start+std::ceil(o.bytes/(512*nm));o.gate=std::max({poolfree[scope],srcfree[o.src],epfree});o.state=2;active_net++;netbytes+=o.bytes;
                uint64_t sampled=std::max<uint64_t>(1,std::ceil(o.bytes/scale)),flits=std::ceil(sampled/flitbytes),offset=0;o.packets=(flits+31)/32;
                while(flits){int n=std::min<uint64_t>(flits,32);events.push({o.start+offset,2,id,packet_id++,n});flits-=n;offset+=n;}
                events.push({o.gate,0,id,0,0});
            }}
        }
        // Retry backpressure each scheduler quantum, retaining controller state.
            for(int ch=0;ch<16;++ch){auto&waiting=memwait[ch];for(auto it=waiting.begin();it!=waiting.end();){Op&o=ops[*it];while(o.next<o.sample&&o.outstanding<max_outstanding_per_op){uint64_t chunk=std::min<uint64_t>(o.sample-o.next,tx);uint64_t nsamples=(o.sample+tx-1)/tx,index=o.next/tx;uint64_t relative=((index*o.bytes/nsamples)/tx)*tx;uint64_t sampled_address=o.address+std::min<uint64_t>(relative,o.bytes-chunk);int original_bank=decode_bank_field(sampled_address,bank_field_shift);int id=o.id;int typ=o.kind=="STORE"?Ramulator::Request::Type::Write:Ramulator::Request::Type::Read;
                    int transaction_id=int(dram_request_id++);
                    bool ok=fronts[ch]->receive_external_requests(typ,(Ramulator::Addr_t)sampled_address,o.owner,[&,id,ch,chunk,transaction_id,submitted=now,address=sampled_address,original_bank](Ramulator::Request&r){Op&x=ops[id];
                if(r.addr_vec.size()!=6)throw std::runtime_error("missing decoded bank address");
                        int mapped_bank=r.addr_vec[2]*4+r.addr_vec[3];bank_mapping_counts[original_bank*16+mapped_bank]++;
                        if(r.first_issue<r.arrive||r.final_issue<r.first_issue||r.depart<r.final_issue){std::ostringstream msg;msg<<"invalid DRAM request lifecycle arrive="<<r.arrive<<" first="<<r.first_issue<<" final="<<r.final_issue<<" depart="<<r.depart<<" row_status="<<r.row_status<<" type="<<r.type_id;throw std::runtime_error(msg.str());}
                        double represented=double(x.bytes)*chunk/x.sample;
                        auto&agg=bank_aggregates[std::make_tuple(ch,r.addr_vec[2],r.addr_vec[3])];
                        agg.transactions++;agg.transactions_with_wait+=r.cross_request_bank_wait>0;agg.represented_bytes+=represented;agg.queue_ticks+=r.first_issue-r.arrive;agg.cross_request_wait_ticks+=r.cross_request_bank_wait;agg.wait_events+=r.cross_request_bank_wait_events;agg.row_command_ticks+=r.final_issue-r.first_issue;agg.completion_ticks+=r.depart-r.final_issue;
                        int layer=decode_layer(x.task);if(layer>=0)layer_bank_wait_ticks[{layer,mapped_bank}]+=r.cross_request_bank_wait;
                        if(r.row_status==0)agg.row_status_0++;else if(r.row_status==1)agg.row_status_1++;else agg.row_status_other++;
                        if(!dram_outstanding||!x.outstanding)throw std::runtime_error("DRAM outstanding underflow");dram_outstanding--;x.outstanding--;
                        if(bank_detail){banklog<<id<<','<<transaction_id<<','<<r.source_id<<','<<ch<<','<<address<<','<<chunk<<','<<represented<<','<<submitted<<','<<memory_tick<<','<<r.arrive<<','<<r.first_issue<<','<<r.final_issue<<','<<r.depart<<','<<(r.first_issue-r.arrive)<<','<<r.cross_request_bank_wait<<','<<r.cross_request_bank_wait_events<<','<<(r.final_issue-r.first_issue)<<','<<(r.depart-r.final_issue)<<','<<r.row_status;
                        for(int level:r.addr_vec)banklog<<','<<level;banklog<<','<<r.type_id<<'\n';}x.received++;if(x.received>x.expected)throw std::runtime_error("duplicate RAM completion");if(x.received==x.expected){x.backend=memory_tick;if(!mem_fault_used&&memhold){mem_fault_used=true;x.gate=std::max(x.gate,now+memhold);events.push({x.gate,0,id,0,0});}check(id);}},int(chunk));
                    if(!ok)break;dram_outstanding++;o.outstanding++;if(o.first<0)o.first=now;o.next+=chunk;
                }if(o.next==o.sample)it=waiting.erase(it);else ++it;}
        }
        if(inflight||network_queue.message_queue_size()){for(auto&r:network.inter_network())r.router_sim_pwr(1.0);}
        if(uint64_t(now)%1000000==0)std::cout<<"cycle "<<now<<" completed "<<completed<<'/'<<ops.size()<<std::endl;
        double next_now=now+1.;
        bool pending_memory=dram_outstanding>0;
        for(const auto&waiting:memwait)pending_memory=pending_memory||!waiting.empty();
        bool pending_network=inflight||active_net||network_queue.message_queue_size();
        if(!thermal.enabled&&!pending_memory&&!pending_network&&ready.empty()&&netwait.empty()&&!events.empty()&&events.top().time>next_now){
            next_now=events.top().time;event_jump_cycles+=uint64_t(next_now-now-1.);event_jump_count++;
            // Preserve Ramulator's internal clock (including refresh/timing state)
            // while bypassing the otherwise empty DAG/NoC scheduler iterations.
            while(memory_tick<=next_now+1e-8){for(int ch=0;ch<16;++ch)memories[ch]->tick();memory_tick+=tck;}
        }
        now=next_now;
    }
    if(packet_id!=packets_done||inflight||active_net)throw std::runtime_error("uncompleted network operations");
    if(dram_outstanding)throw std::runtime_error("uncompleted DRAM operations");
    uint64_t violations=0;for(auto&o:ops){if(o.start+1e-8<o.ready||o.done+1e-8<o.backend||o.done+1e-8<o.gate)violations++;for(int d:o.children)if(ops[d].start+1e-8<o.done)violations++;}
    if(violations)throw std::runtime_error("causal violation");
    thermal.step(totalcycle);
    std::ofstream bankagglog(out+"/bank_aggregate.csv");
    bankagglog<<"partition,bankgroup,bank,transactions,transactions_with_cross_request_wait,represented_bytes,controller_queue_ticks,cross_request_bank_wait_ticks,cross_request_bank_wait_events,row_command_ticks,completion_ticks,row_status_0,row_status_1,row_status_other\n"<<std::setprecision(17);
    for(const auto&entry:bank_aggregates){const auto&key=entry.first;const auto&a=entry.second;bankagglog<<std::get<0>(key)<<','<<std::get<1>(key)<<','<<std::get<2>(key)<<','<<a.transactions<<','<<a.transactions_with_wait<<','<<a.represented_bytes<<','<<a.queue_ticks<<','<<a.cross_request_wait_ticks<<','<<a.wait_events<<','<<a.row_command_ticks<<','<<a.completion_ticks<<','<<a.row_status_0<<','<<a.row_status_1<<','<<a.row_status_other<<'\n';}
    std::ofstream layerbanklog(out+"/layer_bank_wait.csv");layerbanklog<<"decoded_bank,decoder_layer,cross_request_bank_wait_ticks\n"<<std::setprecision(17);
    for(int bank=0;bank<16;++bank)for(int layer=0;layer<48;++layer)layerbanklog<<bank<<','<<layer<<','<<layer_bank_wait_ticks[{layer,bank}]<<'\n';
    std::ofstream mappinglog(out+"/address_mapping.csv");mappinglog<<"original_decoded_bank,mapped_decoded_bank,transactions\n";for(int original=0;original<16;++original)for(int mapped=0;mapped<16;++mapped)if(bank_mapping_counts[original*16+mapped])mappinglog<<original<<','<<mapped<<','<<bank_mapping_counts[original*16+mapped]<<'\n';
    std::ofstream acceleration(out+"/acceleration.json");
    acceleration<<"{\n\"mode\":\"idle-driver-event-jump-v2-ramulator-ticks-preserved\",\"event_jump_count\":"<<event_jump_count<<",\"event_jump_cycles\":"<<event_jump_cycles<<",\"thermal_jump_disabled\":"<<(thermal.enabled?"true":"false")<<"\n}\n";
    PopnetMicroStats::instance().dump(totalcycle);
    std::ofstream manifest(out+"/run_manifest.json");manifest<<std::setprecision(17)<<"{\n\"status\":\"PASS\",\"total_cycles\":"<<totalcycle<<",\"operations\":"<<ops.size()<<",\"completed\":"<<completed<<",\"dependencies\":"<<edgecount<<",\"causal_violations\":"<<violations<<",\"dram_multiplier\":"<<dm<<",\"noc_multiplier\":"<<nm<<",\"architecture_transaction_bytes\":"<<architecture_tx_bytes<<",\"base_memory_bytes_per_cycle\":"<<base_mem_bytes_per_cycle<<",\"dram_tx_bytes\":"<<tx<<",\"dram_tck_ns\":"<<tck<<",\"bank_address_mode\":\""<<bank_address_mode<<"\",\"effective_banks\":"<<effective_banks<<",\"bank_field_shift\":"<<bank_field_shift<<",\"address_mapping_classification\":\"controlled address-mapping stress; not a natural Qwen3 workload\",\"cross_logical_request_multi_outstanding\":true,\"memory_service_policy\":\"per-partition serialized official DeepStack actual Bank service; sampled Ramulator requests validate decoded Bank/Row mechanism\",\"deepstack_timing_enabled\":"<<(!deepstack_timing.empty()?"true":"false")<<",\"deepstack_timed_ops\":"<<deepstack_actual.size()<<",\"represented_mem_bytes\":"<<membytes<<",\"sampled_mem_bytes\":"<<sampledbytes<<",\"represented_remote_noc_bytes\":"<<netbytes<<",\"packets_injected\":"<<packet_id<<",\"packets_completed\":"<<packets_done<<",\"flits_injected\":"<<flits_sent<<",\"mem_hold_applied\":"<<(mem_fault_used?"true":"false")<<",\"net_hold_applied\":"<<(net_fault_used?"true":"false")<<",\"timing_source\":\"last completed micro-DAG operation\",\"model\":\"full-byte official DeepStack Bank service plus persistent sampled Ramulator2 mechanism trace and payload-scaled PopNet; V3.6 execution overlay, not PDK-calibrated hardware timing\"}\n";
    std::cout<<"DONE total_cycles="<<std::setprecision(17)<<totalcycle<<std::endl;return 0;
}catch(const std::exception&e){std::cerr<<"COUPLED FAIL: "<<e.what()<<std::endl;return 2;}}

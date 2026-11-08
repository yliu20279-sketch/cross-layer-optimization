// Artificial causal-solver regression. Not a model/application measurement.
#include "ring_local.h"
#include "sync_protocol.h"
#include "npusim_chiplet_memory.h"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <algorithm>
static std::uint64_t tag(int step,int s,int d){
    return 0x4e4f000003000000ULL|(std::uint64_t(step+1)<<20)|(std::uint64_t(s)<<8)|d;
}
int main(int argc,char**argv){try{
    if(argc!=3)throw std::runtime_error("rank and target config required");
    int n=std::stoi(argv[1]);auto cfg=NPUSim::loadConfig(argv[2]);
    NativeCausalTrace::get().init(n);
    cfg.dram_chiplet_x=n%4;cfg.dram_chiplet_y=4+n/4;
    if(cfg.dram_size_bytes!=2147483648ULL||cfg.sram_per_mac_bytes!=4194304)
        throw std::runtime_error("target capacities changed in real-DRAM unit");
    std::ofstream events("local_events.csv"),posts("posted_descriptors.csv"),comm("communication.csv"),services("exchange_sram_service.csv"),bounds("join_bounds.csv");
    events<<"node,label,event,kind,address,bytes,ops,issue,start,finish\n";
    posts<<"node,op,descriptor,peer,bytes,buffer,metadata_address,post_cycle,local_workspace_limit\n";
    comm<<"node,role,op,descriptor,peer,bytes,buffer,prepare,issue,done,consume_finish\n";
    services<<"node,time,op,request,address,bytes,is_write\n";
    bounds<<"node,step,issue,source,receive,join,applied\n";
    constexpr std::uint64_t bytes=2048,metadata=3900000,flits=65;
    unsigned long long cycle=10000+n*11;
    std::filesystem::create_directories("reports");
    NPUSim::ChipletMemoryClientOptions options;options.self_x=n%4;options.self_y=n/4;
    options.transaction_trace_path="reports/dram_transactions.csv";
    NPUSim::ChipletMemoryClient memory(cfg,options,cycle);
    RingLocal local(cfg,n,bytes,256,events,bytes+32);local.prepareAllGather(cycle);
    for(int step=0;step<15;++step){
        const auto begin=cycle;const auto tx=tag(step,n,(n+1)%16),rx=tag(step,(n+15)%16,n);
        memory.loadTrace(4096+(step%7)*4096,bytes,"artificial_source_materialization");
        local.readTransmitChunk(cycle,(n-step+32)%16,3,step);
        // The same native scheduler and configured SRAM callback as the app.
        NPUSim::NpuEventRecorder recorder;recorder.dmaStore(step+1,metadata,32);
        auto result=NPUSim::scheduleNpuProgramEvents(recorder.events(),cfg,cycle,
            [&](const NPUSim::NpuMemoryRequest&r,std::uint64_t issue){
                services<<n<<','<<issue+1<<','<<step<<','<<step+1<<','<<r.address<<",32,1\n";
                NativeCausalTrace::get().service(issue+1,32);
                return issue+1;
            });
        cycle=result.overall_finish_cycle;const auto issue=cycle;
        posts<<n<<','<<step<<','<<rx<<','<<(n+15)%16<<','<<bytes<<','<<2*16*bytes<<','<<metadata<<','<<issue<<",65536\n";posts.flush();
        NativeCausalTrace::get().release(tx,true,issue);NativeCausalTrace::get().release(rx,false,issue);
        InterChiplet::sendWriteCmd(issue,n%4,n/4,(n+1)%16%4,(n+1)%16/4,bytes,static_cast<long>(tx));
        InterChiplet::sendReadCmd(issue,(n+15)%16%4,(n+15)%16/4,n%4,n/4,bytes,static_cast<long>(rx));
        const auto a=InterChiplet::waitNocCompletion(tx,true),b=InterChiplet::waitNocCompletion(rx,false);
        cycle=std::max<unsigned long long>({a,b,issue+2*flits});
        NativeCausalTrace::get().wait(issue,cycle,tx,rx);
        bounds<<n<<','<<step<<','<<issue<<','<<a<<','<<b<<','<<cycle<<','<<(cycle>std::max(a,b))<<'\n';
        local.copyReceivedChunk(cycle,(n-step-1+32)%16,step);
        comm<<n<<",send,"<<step<<','<<tx<<','<<(n+1)%16<<','<<bytes<<",67584,"<<begin<<','<<issue<<','<<a<<','<<a<<'\n';
        comm<<n<<",receive,"<<step<<','<<rx<<','<<(n+15)%16<<','<<bytes<<",65536,"<<begin<<','<<issue<<','<<b<<','<<cycle<<'\n';comm.flush();
    }
    events.flush();services.flush();bounds.flush();memory.shutdown();InterChiplet::sendCycleCmd(cycle);return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}

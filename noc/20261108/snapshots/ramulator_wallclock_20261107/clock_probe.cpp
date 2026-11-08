#include "ramulator2_wrapper.h"
#include <ramulator/base/config.h>
#include <ramulator/base/factory.h>
#include <ramulator/base/request.h>
#include <ramulator/frontend/i_frontend.h>
#include <ramulator/memory_system/i_memory_system.h>
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>

// Independent direct-engine reference. It does not call any wrapper clock
// conversion, advanceTo, runAtGlobal, or run method.
class DirectReference {
    Ramulator::IFrontEnd* frontend_;
    Ramulator::IMemorySystem* memory_;
    std::uint64_t tick_=0;
public:
    explicit DirectReference(const char* path){
        auto config=Ramulator::Config::parse_config_file(path);
        frontend_=Ramulator::Factory::create_frontend(config);
        memory_=Ramulator::Factory::create_memory_system(config);
        if(!frontend_||!memory_)throw std::runtime_error("reference factory failed");
        frontend_->connect_memory_system(memory_);memory_->connect_frontend(frontend_);
        if(memory_->get_tx_bytes()!=32||memory_->get_tCK()!=1.25)throw std::runtime_error("unexpected frozen memory geometry/clock");
    }
    ~DirectReference(){frontend_->finalize();memory_->finalize();delete memory_;delete frontend_;}
    std::pair<std::uint64_t,std::uint64_t> submit(bool write,std::uint64_t address,std::uint64_t bytes,std::uint64_t arrival){
        // Exact rational tCK=5/4 ns, independent of the candidate's floating
        // point conversion: ceil(arrival * 4/5).
        const auto target=(arrival*4+4)/5;
        while(tick_<target){memory_->tick();++tick_;}
        const auto begin=tick_;std::uint64_t cursor=address,accepted=0,completed=0;
        while(cursor<address+bytes||completed<accepted){
            while(cursor<address+bytes){
                auto count=std::min<std::uint64_t>(address+bytes-cursor,32-cursor%32);
                if(!frontend_->receive_external_requests(write?Ramulator::Request::Type::Write:Ramulator::Request::Type::Read,
                     cursor,0,[&](Ramulator::Request&){++completed;},static_cast<int>(count)))break;
                ++accepted;cursor+=count;
            }
            if(cursor>=address+bytes&&completed>=accepted)break;
            memory_->tick();++tick_;
            if(tick_-begin>2000000)throw std::runtime_error("reference request timeout");
        }
        return {begin,tick_};
    }
};
int main(int argc,char**argv){
    try{
        if(argc!=3)throw std::runtime_error("config csv_output required");
        DirectReference reference(argv[1]);memory::Ramulator2Wrapper candidate(argv[1]),legacy(argv[1]);
        std::ofstream out(argv[2]);if(!out)throw std::runtime_error("probe CSV unavailable");
        out<<"request,arrival,address,bytes,is_write,reference_start_tick,reference_end_tick,candidate_start_tick,candidate_end_tick,idle_ticks,global_done_cycle,legacy_back_to_back_service_ticks\n";
        std::uint64_t done=0,total_idle=0;int changed=0;
        const std::uint64_t gaps[]{0,17,3900,20000};
        const std::uint64_t sizes[]{32,128,4096};
        for(int i=0;i<48;++i){
            auto arrival=done+gaps[i%4];auto address=std::uint64_t(4096+(i%7)*2048+(i%3)*16);
            auto bytes=sizes[i%3];const bool write=i%5==0;
            auto expected=reference.submit(write,address,bytes,arrival);
            auto got=candidate.runAtGlobal(write,address,bytes,arrival,1.25);
            auto old=legacy.run(write,address,bytes);
            const auto expected_global=(expected.second*5+3)/4;
            if(got.start_tick!=expected.first||got.end_tick!=expected.second||got.global_done_cycle!=expected_global)
                throw std::runtime_error("direct-engine wall-clock comparison failed at request "+std::to_string(i));
            if(got.global_done_cycle<arrival||candidate.currentCycle()!=expected.second)
                throw std::runtime_error("wall-clock causality failed");
            if(old!=expected.second-expected.first)++changed;
            total_idle+=got.idle_ticks;done=got.global_done_cycle;
            out<<i<<','<<arrival<<','<<address<<','<<bytes<<','<<write<<','<<expected.first<<','<<expected.second<<','
                <<got.start_tick<<','<<got.end_tick<<','<<got.idle_ticks<<','<<got.global_done_cycle<<','<<old<<'\n';
        }
        if(!total_idle)throw std::runtime_error("test never exercised idle DRAM ticks");
        const auto before=candidate.currentCycle();candidate.advanceTo(0);
        if(candidate.currentCycle()!=before)throw std::runtime_error("idle advance rewound physical time");
        bool rejected=false;try{candidate.runAtGlobal(false,4096,32,done,1.0);}catch(const std::runtime_error&){rejected=true;}
        if(!rejected||candidate.currentCycle()!=before)throw std::runtime_error("invalid clock scale not rejected without side effects");
        std::cout<<"PASS direct native engine: 48 artificial requests, idle_ticks="<<total_idle
                 <<",service_differences_from_back_to_back="<<changed<<"; not application performance\n";
    }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}

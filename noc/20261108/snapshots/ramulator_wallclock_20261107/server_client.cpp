#include "npusim_chiplet_memory.h"
#include "sync_protocol.h"
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>

int main(int argc,char**argv){
    try{
        if(argc!=3)throw std::runtime_error("rank target_config required");
        const int rank=std::stoi(argv[1]);if(rank<0||rank>=16)throw std::runtime_error("bad unit rank");
        auto cfg=NPUSim::loadConfig(argv[2]);cfg.dram_chiplet_x=rank%4;cfg.dram_chiplet_y=4+rank/4;
        if(cfg.dram_size_bytes!=2147483648ULL||cfg.sram_per_mac_bytes!=4194304)
            throw std::runtime_error("original target capacities changed");
        std::filesystem::create_directories("reports");unsigned long long cycle=1;
        NPUSim::ChipletMemoryClientOptions options;options.self_x=rank%4;options.self_y=rank/4;
        options.transaction_trace_path="reports/dram_transactions.csv";
        NPUSim::ChipletMemoryClient memory(cfg,options,cycle);
        const std::uint64_t gaps[]{0,17,3900,20000},sizes[]{32,128,4096};
        for(int i=0;i<12;++i){
            cycle+=gaps[(i+rank)%4];
            const auto address=std::uint64_t(4096+(i%7)*2048+(i%3)*16),bytes=sizes[i%3];
            if(i%5==0)memory.storeTrace(address,bytes,"artificial_server_clock_unit");
            else memory.loadTrace(address,bytes,"artificial_server_clock_unit");
        }
        memory.shutdown();std::cout<<"[SERVER_CLOCK_UNIT] "<<rank<<' '<<cycle<<'\n';
        InterChiplet::sendCycleCmd(cycle);
    }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}

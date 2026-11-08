#include "program_fences.h"
#include "/mnt/sdb1/h4567/noc_hb_transport_20261108/direct_reference.h"
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <stdexcept>
void need(bool x,const char*s){if(!x)throw std::runtime_error(s);}
int main(int argc,char**argv){try{
    if(argc!=3)throw std::runtime_error("config completion_order required");
    const auto id0=0x4e50000000100000ULL,id1=0x4e50100000100000ULL,id2=0x4e50000000200000ULL;
    {std::ofstream f("memory_fixture.txt");
     f<<"dram 0 1 0 100 0 4096 32 "<<id0<<" 100000\nservice 0 1 1 32 100001\n"
      <<"fence 0 2 1 7 101 102 200000\n"
      <<"dram 0 3 2 5 1 8192 4096 "<<id2<<" 300000\nservice 0 3 1 32 300001\nrelease 0 3 201 1 3\n"
      <<"dram 1 1 0 200 1 4096 1024 "<<id1<<" 100000\nrelease 1 1 301 0 2\n";}
    setenv("NOC_PROGRAM_FENCES","memory_fixture.txt",1);setenv("NOC_CAUSAL_COMMAND_CLOCK","1",1);
    setenv("NOC_DRAM_PROGRAM","1",1);setenv("NOC_DRAM_CONFIG",argv[1],1);
    setenv("LEGOSIM_HB_SERVICE_BYTES","128",1);setenv("LEGOSIM_HB_SERVICE_CYCLES","5",1);
    auto occupancy=[](std::uint64_t bytes){return (bytes*5+127)/128;};
    DirectReference ref0(argv[1]),ref1(argv[1]);
    auto load=ref0.submit(false,4096,32,102);auto load_done=(load.second*5+3)/4+occupancy(32);
    auto store1=ref1.submit(true,4096,1024,200+2+occupancy(1024));
    auto store1_done=(store1.second*5+3)/4+occupancy(16);
    auto& p=ProgramFences::get();need(p.issue_time(0,201,true,0)==-1,"memory descendants resolved before NoC wait");
    need(p.issue_time(1,301,false,0)==long(store1_done+2),"independent initial STORE differs");
    if(std::string(argv[2])=="reverse"){
        p.complete(0,102,false,load_done+200);p.complete(0,101,true,load_done+100);
    }else{p.complete(0,101,true,load_done+100);p.complete(0,102,false,load_done+200);}
    const auto store0_issue=load_done+200+5;
    auto store0=ref0.submit(true,8192,4096,store0_issue+2+occupancy(4096));
    const auto store0_done=(store0.second*5+3)/4+occupancy(16);
    need(p.issue_time(0,201,true,0)==long(store0_done+3),"NoC->native DRAM->next command differs from direct engine");
    need(p.busy(0,store0_done+1),"actual post-DRAM SRAM service lost");p.finish();
    std::cout<<"PASS independent native DRAM causal program, actual completion order, precise transport\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}

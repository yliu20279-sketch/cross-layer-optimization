#include "net_bench.h"
#include "net_delay.h"
#include <fstream>
#include <iostream>
#include <stdexcept>
static void require(bool x,const char*s){if(!x)throw std::runtime_error(s);}
int main(){try{
    for(bool absolute:{false,true})for(bool enabled:{false,true}){
        setenv("LEGOSIM_ABSOLUTE_NOC_COMPLETIONS",absolute?"1":"0",1);
        if(enabled)setenv("LEGOSIM_RENDEZVOUS_FLIT_BYTES","32",1);else unsetenv("LEGOSIM_RENDEZVOUS_FLIT_BYTES");
        for(long tag:{long(0x4e4f800000000001ULL),long(0x4e50000000000001ULL)}){
            {std::ofstream f("fixture.txt");f<<"100 0 1 "<<tag<<" 2 135 160\n";}
            NetworkDelayStruct map;map.loadDelayInfo("fixture.txt",1,4);
            InterChiplet::SyncCommand w{},r{};w.m_src={0,0};w.m_dst={1,0};w.m_desc=tag;w.m_cycle=100;w.m_nbytes=4096;r=w;r.m_cycle=10000;
            auto v=map.getEndCycle(w,r);
            if(enabled&&tag==long(0x4e4f800000000001ULL)){
                require(SRC_DELAY(v)>=10129&&DST_DELAY(v)>SRC_DELAY(v),"late READ violated rendezvous causality");
            }else require(SRC_DELAY(v)==235&&DST_DELAY(v)==10000,"legacy or vertical behavior changed");
        }
    }
    setenv("LEGOSIM_RENDEZVOUS_FLIT_BYTES","32",1);
    {std::ofstream f("fixed_fixture.txt");f<<"100 0 1 "<<long(0x4e4f800000000001ULL)<<" 2 2061 2162\n";}
    for(bool absolute:{false,true}){
        setenv("LEGOSIM_ABSOLUTE_NOC_COMPLETIONS",absolute?"1":"0",1);
        NetworkDelayStruct map;map.loadDelayInfo("fixed_fixture.txt",1,4);
        InterChiplet::SyncCommand w{},r{};w.m_src={0,0};w.m_dst={1,0};w.m_desc=long(0x4e4f800000000001ULL);w.m_cycle=100;w.m_nbytes=32768;r=w;
        auto v=map.getEndCycle(w,r);require(SRC_DELAY(v)==2161&&DST_DELAY(v)==2262,"fixed point was modified");
    }
    std::cout<<"PASS rendezvous bounds, legacy/vertical isolation, fixed point equivalence\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}

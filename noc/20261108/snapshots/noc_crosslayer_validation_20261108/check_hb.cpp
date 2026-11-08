#include "net_bench.h"
#include "net_delay.h"
#include <iostream>
#include <stdexcept>
void require(bool b,const char* s){if(!b)throw std::runtime_error(s);}
int main(){try{
    InterChiplet::SyncCommand w{},r{};w.m_src={0,0};w.m_dst={0,4};
    w.m_cycle=100;w.m_nbytes=32;w.m_desc=long(0x4e50000000100000ULL);r=w;r.m_cycle=111;
    unsetenv("LEGOSIM_HB_SERVICE_BYTES");unsetenv("LEGOSIM_HB_SERVICE_CYCLES");
    NetworkDelayStruct legacy;auto v=legacy.getEndCycle(w,r);
    require(SRC_DELAY(v)==116&&DST_DELAY(v)==116,"legacy default changed");
    setenv("LEGOSIM_HB_SERVICE_BYTES","128",1);setenv("LEGOSIM_HB_SERVICE_CYCLES","5",1);
    for(long bytes:{1,16,32,33,127,128,129,2048,4096}){
        w.m_nbytes=r.m_nbytes=bytes;NetworkDelayStruct d;v=d.getEndCycle(w,r);
        const auto expected=111+(bytes*5+127)/128;
        require(SRC_DELAY(v)==expected&&DST_DELAY(v)==expected,"rational occupancy mismatch");
        require(d.getDefaultEndCycle(w)==100+(bytes*5+127)/128,"single-command occupancy mismatch");
    }
    w.m_desc=r.m_desc=long(0x4e4f000000100000ULL);w.m_nbytes=r.m_nbytes=32;
    unsetenv("LEGOSIM_RENDEZVOUS_FLIT_BYTES");NetworkDelayStruct horizontal;v=horizontal.getEndCycle(w,r);
    require(SRC_DELAY(v)==116&&DST_DELAY(v)==116,"horizontal fallback changed");
    w.m_desc=r.m_desc=long(0x4e50000000100000ULL);
    for(const char* invalid:{"0","-1","1x","","18446744073709551616"}){
        setenv("LEGOSIM_HB_SERVICE_BYTES",invalid,1);bool rejected=false;
        try{NetworkDelayStruct d;d.getEndCycle(w,r);}catch(const std::runtime_error&){rejected=true;}
        require(rejected,"invalid HB ratio accepted");
    }
    unsetenv("LEGOSIM_HB_SERVICE_BYTES");bool rejected=false;
    try{NetworkDelayStruct d;d.getEndCycle(w,r);}catch(const std::runtime_error&){rejected=true;}
    require(rejected,"incomplete HB ratio accepted");
    setenv("LEGOSIM_HB_SERVICE_BYTES","128",1);r.m_nbytes=16;rejected=false;
    try{NetworkDelayStruct d;d.getEndCycle(w,r);}catch(const std::runtime_error&){rejected=true;}
    require(rejected,"mismatched byte counts accepted");
    std::cout<<"PASS HB exact rational occupancy, legacy/horizontal isolation, invalid-input rejection\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}

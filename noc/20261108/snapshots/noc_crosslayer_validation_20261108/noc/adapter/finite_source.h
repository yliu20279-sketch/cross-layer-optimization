#pragma once
#include "flit.h"
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <stdexcept>
#include <string>

// Optional finite, SRAM-backed source staging contract. No extra wire/port.
inline long finite_source_capacity(){
    static long capacity=[](){
        const char* v=std::getenv("NOC_SOURCE_CAPACITY_FLITS");
        if(!v)return 0L;
        std::size_t used=0;long n=std::stol(v,&used);
        if(used!=std::string(v).size()||n<=0)throw std::runtime_error("invalid source capacity");
        return n;
    }();return capacity;
}
inline void finite_source_record(const char* event,long node,const flit_template& f,
                                 time_type now,long occupancy){
    if(!finite_source_capacity())return;
    static const char* path=std::getenv("NOC_SOURCE_LOG");
    if(!path)throw std::runtime_error("finite source requires audit log");
    static std::ofstream log(path);static bool header=false;
    if(!log)throw std::runtime_error("cannot open finite source log");
    if(!header){log<<"time,event,node,packet,ordinal,occupancy,tail,start,send_finish\n";header=true;}
    log<<std::setprecision(17)<<now<<','<<event<<','<<node<<','<<f.getPacketId()<<','<<f.sequence()
       <<','<<occupancy<<','<<isTail(f.type())<<','<<f.start_time()<<','<<f.send_finish_time()<<'\n';
}

#pragma once
#include <array>
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <stdexcept>
#include "global_define.h"

// Research service overlay. HB command/reply framing is charged explicitly;
// fixed HB latency remains unknown and is NOT certified by this overlay.
namespace swe_domain {
enum Kind { horizontal=0, hb=1, pcie=2 };
inline bool enabled(){return std::getenv("SWE_DOMAIN_SERVICES")!=nullptr;}
inline int id(const InterChiplet::AddrType&a){return DIM_X(a)+4*DIM_Y(a);}
inline Kind kind(int s,int d){
 if(s>=0&&s<=16&&d>=0&&d<=16)return horizontal;
 if((s>=0&&s<16&&d==s+32)||(d>=0&&d<16&&s==d+32))return hb;
 if((s==48&&d==16)||(s==16&&d==48))return pcie;
 throw std::runtime_error("unmapped service-domain endpoint pair");
}
struct State {std::array<double,16> hb_free{};std::array<double,2> pcie_free{};double host_free=0;std::ofstream log,feedback_log,clock_log;int round=0;};
inline State& state(){static State s;return s;}
inline void reset(){if(!enabled())return;auto&s=state();s.hb_free.fill(0);s.pcie_free.fill(0);s.host_free=0;if(s.log.is_open())s.log.close();if(s.feedback_log.is_open())s.feedback_log.close();s.log.open("domain_service_round"+std::to_string(++s.round)+".csv");s.log<<"domain,src,dst,descriptor,bytes,ready,start,complete,host_complete,wire_complete\n";s.feedback_log.open("noc_feedback_round"+std::to_string(s.round)+".csv");s.feedback_log<<std::setprecision(17)<<"src,dst,descriptor,writer_ready,reader_ready,profile_applied\n";s.log<<std::setprecision(17);if(s.clock_log.is_open())s.clock_log.close();s.clock_log.open("clock_round"+std::to_string(s.round)+".csv");s.clock_log<<std::setprecision(17)<<"src,dst,descriptor,native_ticks,clock_ratio,global_ns\n";}
inline void feedback(const InterChiplet::SyncCommand&w,const InterChiplet::SyncCommand&r,bool applied){if(!enabled())return;state().feedback_log<<id(w.m_src)<<','<<id(w.m_dst)<<','<<w.m_desc<<','<<w.m_cycle<<','<<r.m_cycle<<','<<applied<<'\n';state().feedback_log.flush();}
inline InterChiplet::TimeType tick(double value){return static_cast<InterChiplet::TimeType>(enabled()?std::ceil(value):value);}
inline void observe_clock(const InterChiplet::SyncCommand&c,double native){if(enabled()&&(c.m_type==InterChiplet::SC_READ||c.m_type==InterChiplet::SC_WRITE)){auto&s=state();s.clock_log<<id(c.m_src)<<','<<id(c.m_dst)<<','<<c.m_desc<<','<<native<<','<<c.m_clock_rate<<','<<c.m_cycle<<'\n';s.clock_log.flush();}}
inline double complete(const InterChiplet::SyncCommand&w,const InterChiplet::SyncCommand&r){
 int src=id(w.m_src),dst=id(w.m_dst);Kind k=kind(src,dst);auto&s=state();double ready=std::ceil(std::max(w.m_cycle,r.m_cycle)),start=ready,done=ready,h=ready,wire=ready;
 if(w.m_nbytes<=0)throw std::runtime_error("invalid domain payload size");
 if(k==hb){int n=src<16?src:dst;start=std::max(ready,s.hb_free[n]);done=start+std::ceil(w.m_nbytes*5.0/128.0);s.hb_free[n]=done;}
 else if(k==pcie){
  int direction=src==48?0:1;
  if(direction==0){start=std::max(ready,s.host_free);h=start+60+std::ceil(w.m_nbytes*5.0/64.0);s.host_free=h;wire=std::max(h,s.pcie_free[direction])+std::ceil(w.m_nbytes*25.0/1376.0);s.pcie_free[direction]=wire;done=wire+250;}
  else {start=std::max(ready,s.pcie_free[direction]);wire=start+std::ceil(w.m_nbytes*25.0/1376.0);s.pcie_free[direction]=wire;h=std::max(wire+250,s.host_free)+60+std::ceil(w.m_nbytes*5.0/64.0);s.host_free=h;done=h;}
 } else throw std::runtime_error("horizontal traffic must use PopNet feedback");
 s.log<<(k==hb?"HB_RPC":"HOST_PCIE")<<','<<src<<','<<dst<<','<<w.m_desc<<','<<w.m_nbytes<<','<<ready<<','<<start<<','<<done<<','<<h<<','<<wire<<'\n';s.log.flush();return done;
}
}

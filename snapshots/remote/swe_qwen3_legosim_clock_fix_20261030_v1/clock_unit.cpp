#include "domain_service.h"
#include <cassert>
#include <iostream>
int main(){setenv("SWE_DOMAIN_SERVICES","1",1);swe_domain::reset();
 InterChiplet::SyncCommand w,r;w.m_src={0,12};w.m_dst={0,4};w.m_nbytes=256;w.m_desc=0;w.m_cycle=123.0/2.5;r=w;r.m_cycle=0;
 auto done=swe_domain::complete(w,r);assert(done==385);assert(swe_domain::tick(done*2.5)==963);assert(963.0/2.5>=done);
 for(long ns=0;ns<10001;ns++)assert(swe_domain::tick(ns*2.5)/2.5>=ns);
 assert(62*1.25==77.5 && std::ceil(62*1.25)==78);
 std::cout<<"PASS_CLOCK_DOMAIN_CEILING_AND_NO_EARLY_WAKE\n";
}

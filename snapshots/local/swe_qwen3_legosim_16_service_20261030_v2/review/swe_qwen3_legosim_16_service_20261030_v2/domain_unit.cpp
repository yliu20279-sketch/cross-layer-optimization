#include "domain_service.h"
#include <cassert>
#include <iostream>
InterChiplet::SyncCommand command(int s,int d,int bytes,double cycle=0){InterChiplet::SyncCommand c;c.m_src={s%4,s/4};c.m_dst={d%4,d/4};c.m_nbytes=bytes;c.m_cycle=cycle;c.m_desc=0;return c;}
int main(){setenv("SWE_DOMAIN_SERVICES","1",1);swe_domain::reset();
 auto a=command(0,32,128);assert(swe_domain::complete(a,a)==5);assert(swe_domain::complete(a,a)==10);
 auto b=command(1,33,128);assert(swe_domain::complete(b,b)==5);
 auto h=command(48,16,256);assert(swe_domain::complete(h,h)==335);
 auto d=command(16,48,256);assert(swe_domain::complete(d,d)==335);
 bool bad=false;try{swe_domain::kind(48,0);}catch(const std::runtime_error&){bad=true;}assert(bad);
 bad=false;try{swe_domain::kind(0,33);}catch(const std::runtime_error&){bad=true;}assert(bad);
 assert(swe_domain::kind(16,15)==swe_domain::horizontal);std::cout<<"PASS_DOMAIN_SERVICE_UNIT_AND_TWO_ENDPOINT_NEGATIVES\n";
}

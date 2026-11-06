#include "lifetime_allocator.h"
#include <cassert>
#include <iostream>
template<class F> void rejects(F f){bool rejected=false;try{f();}catch(const std::runtime_error&){rejected=true;}assert(rejected);}
int main(){
 LifetimeAllocator a;std::uint64_t y[12]={},v;
 a.allocate(64,1,1,y);v=y[1];a.owner(1,v,true,y);assert(y[2]==1);
 a.read_complete(1,v,0,y);a.barrier(4,y);assert(y[0]==0);
 a.inspect(y);assert(y[0]==1&&y[1]==64&&y[2]==1);
 rejects([&]{a.owner(1,v+1,false,y);});
 a.owner(1,v,false,y);assert(y[2]==0);
 rejects([&]{a.owner(1,v,false,y);});
 a.barrier(4,y);assert(y[0]==1);a.inspect(y);
 assert(y[0]==0&&y[1]==0&&y[2]==0&&y[3]==208ULL*1024*1024);
 rejects([&]{a.owner(1,v,true,y);});
 a.allocate(64,1,0,y);assert(y[0]==32ULL*1024*1024&&y[1]!=v);
 rejects([&]{a.owner(1,v,true,y);});
 auto newer=y[1];a.owner(1,newer,true,y);a.owner(1,newer,true,y);
 a.owner(1,newer,false,y);a.barrier(4,y);assert(y[0]==0);
 a.owner(1,newer,false,y);a.barrier(4,y);assert(y[0]==1);
 a.inspect(y);assert(y[3]==208ULL*1024*1024);
 std::cout<<"PASS_CPU_ONLY_OWNER_CONTROLS: pin blocks reclaim; version/underflow guards; multiple owners; coalesced arena\n";
}

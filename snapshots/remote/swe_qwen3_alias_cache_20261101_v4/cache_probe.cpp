#include <cstdlib>
#include <cstring>
#include <fstream>
#include "sim_api.h"
#include "cache_evict.h"
volatile std::uint64_t result=0;
static inline void marker(unsigned long a){unsigned long cmd=4,b=0;asm volatile("xchg %%bx,%%bx" : "+a"(cmd),"+b"(a),"+c"(b) : : "memory");}
int main(int argc,char**argv){LruSoftwareMaintenance m;void*raw=nullptr;if(posix_memalign(&raw,524288,16384))return 2;auto p=(volatile std::uint64_t*)raw;std::memset(raw,0,16384);
 SimRoiStart();
 for(int which=0;which<2;which++){
  if(which)p[0]=8;result=p[0];marker(100+which);std::uint64_t sum=0;for(int j=0;j<2048;j++)sum+=p[0];result=sum;marker(110+which);
  if(which)p[0]=37;
  marker(120+which);m.maintain(raw,64);marker(130+which);sum=0;for(int j=0;j<2048;j++)sum+=p[0];result=sum;marker(140+which);
  if(result!=2048*(which?37:0))return 3;
 }
 SimRoiEnd();std::ofstream(argv[1])<<"PASS_FUNCTIONAL_CLEAN_DIRTY_MAINTENANCE\n";free(raw);return 0;}

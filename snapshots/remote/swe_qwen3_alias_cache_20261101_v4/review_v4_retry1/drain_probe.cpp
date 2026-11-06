#include <cstdlib>
#include <cstring>
#include <fstream>
#include "sim_api.h"
#include "cache_evict.h"
volatile std::uint64_t drain_result=0;
static inline void mark(unsigned long a){unsigned long cmd=4,b=0;asm volatile("xchg %%bx,%%bx" : "+a"(cmd),"+b"(a),"+c"(b) : : "memory");}
static inline unsigned long drain(){unsigned long cmd=5,a=0x534d4344UL,b=0x445241494eUL;asm volatile("xchg %%bx,%%bx" : "+a"(cmd),"+b"(a),"+c"(b) : : "memory");return cmd;}
int main(int argc,char**argv){
 if(argc!=2)return 2;LruSoftwareMaintenance maintenance;void* raw=nullptr;
 if(posix_memalign(&raw,524288,1048576))return 3;std::memset(raw,0,1048576);
 auto p=(volatile std::uint64_t*)((unsigned char*)raw+8191*64+56);
 SimRoiStart();
 for(unsigned c=0;c<3;c++){
  p[0]=11+c;p[1]=21+c;p[9]=31+c;
  std::uint64_t expected=p[0]+p[1]+p[9],sum=0;
  mark(100+c*10);for(unsigned j=0;j<2048;j++)sum+=p[0]+p[1]+p[9];drain_result=sum;mark(101+c*10);
  if(c==1){p[0]=81;p[1]=82;p[9]=83;expected=246;}
  mark(102+c*10);
  if(c<2)maintenance.maintain((const void*)p,136);
  mark(103+c*10);
  if(c<2 && drain()!=0x534d4344UL)return 4;
  mark(104+c*10);sum=0;for(unsigned j=0;j<2048;j++)sum+=p[0]+p[1]+p[9];drain_result=sum;mark(105+c*10);
  if(sum!=2048*expected)return 5;
 }
 SimRoiEnd();std::ofstream(argv[1])<<"PASS_FUNCTIONAL_QUEUE_DRAIN_AND_NO_MAINTENANCE_CONTROL\n";free(raw);return 0;
}

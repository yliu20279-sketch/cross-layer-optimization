#include <fstream>
#include "sim_api.h"
int main(int argc,char**argv){if(argc!=2)return 2;SimRoiStart();for(int i=0;i<100;i++)asm volatile("vxorps %%xmm0,%%xmm0,%%xmm0":::"xmm0");SimRoiEnd();std::ofstream(argv[1])<<"NEGATIVE_AVX_EXECUTED_EXPECT_ISA_AUDIT_REJECTION\n";return 0;}

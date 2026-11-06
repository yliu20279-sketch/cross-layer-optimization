#include <immintrin.h>
#include <fstream>
#include "sim_api.h"
__attribute__((noinline)) void op(const float*x,float*y){__m512 a=_mm512_loadu_ps(x);_mm512_storeu_ps(y,_mm512_add_ps(a,_mm512_set1_ps(1.0f)));}
int main(int argc,char**argv){float x[16],y[16];for(int i=0;i<16;++i)x[i]=i+argc;SimRoiStart();op(x,y);SimRoiEnd();std::ofstream(argv[1],std::ios::binary).write((char*)y,sizeof(y));return 0;}
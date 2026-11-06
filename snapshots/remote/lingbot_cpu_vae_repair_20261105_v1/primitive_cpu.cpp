#include "tf32_fda.h"
extern "C" void primitive(const float*a,const float*b,float*y,int n){for(int i=0;i<n;i++)y[i]=hw_block_fma(0,a+8*i,b+8*i,8);}

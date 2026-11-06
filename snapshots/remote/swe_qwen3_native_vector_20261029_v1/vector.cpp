#include <cstdint>
#include <cstring>
static float decode(uint16_t v){uint32_t u=uint32_t(v)<<16;float x;memcpy(&x,&u,4);return x;}
static uint16_t encode(float x){uint32_t u;memcpy(&u,&x,4);if((u&0x7fffffff)>0x7f800000)return uint16_t((u>>16)|64);return uint16_t((u+0x7fff+((u>>16)&1))>>16);}
extern "C" void binary(const uint16_t*a,const uint16_t*b,uint16_t*y,int n,int mul){for(int i=0;i<n;++i){float x=decode(a[i]),z=decode(b[i]);float r=mul?x*z:x+z;y[i]=encode(r);}}

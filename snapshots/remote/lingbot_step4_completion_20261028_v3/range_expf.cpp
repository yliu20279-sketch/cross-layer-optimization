// FP32 range reduction from installed libdevice IR, host exp2 replacement.
// Host exp2f is NOT certified as NVIDIA ex2.approx.ftz. No row/ID lookup.
#include <cmath>
#include <cfenv>
#include <cstdint>
#include <cstring>
#include <cstddef>
#pragma STDC FENV_ACCESS ON
static float f(uint32_t x){float v;std::memcpy(&v,&x,4);return v;}
static uint32_t u(float v){uint32_t x;std::memcpy(&x,&v,4);return x;}
static float down_fma(float a,float b,float c){
 std::fesetround(FE_DOWNWARD);volatile float y=std::fmaf(a,b,c);
 std::fesetround(FE_TONEAREST);return y;
}
static float portable_expf(float a){
 const float hi=f(1069066811u),lo=f(849703008u),magic=f(1262485504u);
 const float scale_arg=hi/252.0f;
 float p=std::fmaf(a,scale_arg,0.5f);
 p=std::fmin(std::fmax(p,0.0f),1.0f);
 float base=(magic-126.0f)+127.0f;
 float n=down_fma(p,252.0f,base);
 float shift=n-(magic+127.0f);
 float residual=std::fmaf(a,hi,-shift);
 residual=std::fmaf(a,lo,residual);
 float scale=f(u(n)<<23);
 return std::exp2(residual)*scale;
}
extern "C" void sigmoid_range(const float*x,float*y,std::size_t count){
 std::fesetround(FE_TONEAREST);
 for(std::size_t i=0;i<count;++i){float ex=portable_expf(-x[i]);float den=1.0f+ex;y[i]=1.0f/den;}
}

// CPU-only software compatibility layer. FP32 values, integer profile indices.
// The complete architecture EX2 domain is independent of model/route data.
#include <cstdint>
#include <cstring>
#include <cmath>
#include <cfenv>
#include <cstddef>
#include <string>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#pragma STDC FENV_ACCESS ON
static const uint32_t* ex2=nullptr;
static int ex2fd=-1;
static float f(uint32_t u){float x;std::memcpy(&x,&u,4);return x;}
static uint32_t u(float x){uint32_t v;std::memcpy(&v,&x,4);return v;}
extern "C" int profile_math_open(const char* directory){
 std::string path=std::string(directory)+"/ex2_all_f32.raw";
 ex2fd=open(path.c_str(),O_RDONLY);if(ex2fd<0)return -1;
 struct stat st;if(fstat(ex2fd,&st)||uint64_t(st.st_size)!=(1ull<<34))return -2;
 void* p=mmap(nullptr,1ull<<34,PROT_READ,MAP_SHARED,ex2fd,0);if(p==MAP_FAILED)return -3;
 ex2=static_cast<const uint32_t*>(p);return 0;
}
static float down(float a,float b,float c){
 std::fesetround(FE_DOWNWARD);volatile float y=std::fmaf(a,b,c);
 std::fesetround(FE_TONEAREST);return y;
}
static float compat_exp(float a){
 const float hi=f(1069066811u),lo=f(849703008u),magic=f(1262485504u);
 float scaled=hi/252.0f;
 float p=std::fmaf(a,scaled,0.5f);p=std::fmin(std::fmax(p,0.0f),1.0f);
 float n=down(p,252.0f,(magic-126.0f)+127.0f);
 float shift=n-(magic+127.0f);
 float residual=std::fmaf(a,hi,-shift);residual=std::fmaf(a,lo,residual);
 float scale=f(u(n)<<23);return f(ex2[u(residual)])*scale;
}
extern "C" int profile_exp(const float* x,float* y,std::size_t n){
 if(!ex2)return -1;std::fesetround(FE_TONEAREST);
 for(std::size_t i=0;i<n;++i)y[i]=compat_exp(x[i]);return 0;
}
extern "C" int profile_sigmoid(const float* x,float* y,std::size_t n){
 if(!ex2)return -1;std::fesetround(FE_TONEAREST);
 for(std::size_t i=0;i<n;++i){float e=compat_exp(-x[i]);float d=1.0f+e;y[i]=1.0f/d;}return 0;
}
extern "C" int profile_silu(const float* x,float* y,std::size_t n){
 if(!ex2)return -1;std::fesetround(FE_TONEAREST);
 for(std::size_t i=0;i<n;++i){float e=compat_exp(-x[i]);float d=1.0f+e;y[i]=x[i]/d;}return 0;
}

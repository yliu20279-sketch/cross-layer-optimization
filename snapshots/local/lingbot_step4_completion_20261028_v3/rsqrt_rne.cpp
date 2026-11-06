// Registered positive-normal FP32 reciprocal-square-root software primitive.
// FP32 candidate/output; integer midpoint decisions avoid FP64 arithmetic.
#include <cmath>
#include <cstdint>
#include <cstring>
#include <cstddef>
static uint32_t bits(float x){uint32_t u;std::memcpy(&u,&x,4);return u;}
static float value(uint32_t u){float x;std::memcpy(&x,&u,4);return x;}
static int expo(uint32_t u){return int((u>>23)&255)-127-23;}
static uint32_t sig(uint32_t u){return (u&0x7fffff)|0x800000;}
static int midpoint_cmp(uint32_t x,uint32_t a,uint32_t b){
 int ea=expo(a),eb=expo(b),em=ea<eb?ea:eb;
 uint64_t t=(uint64_t(sig(a))<<(ea-em))+(uint64_t(sig(b))<<(eb-em));
 unsigned __int128 product=static_cast<unsigned __int128>(sig(x))*t*t;
 int shift=-(expo(x)+2*(em-1));
 if(shift<0||shift>=128)return 9;
 unsigned __int128 one=static_cast<unsigned __int128>(1)<<shift;
 return product<one?-1:(product>one?1:0);
}
extern "C" int rsqrt_rne_fp32(const float*x,float*y,std::size_t count){
 for(std::size_t i=0;i<count;++i){
  uint32_t u=bits(x[i]);if((u>>31)||((u>>23)&255)==0||((u>>23)&255)==255)return int(i)+1;
  uint32_t r=bits(1.0f/std::sqrt(x[i]));
  if(((r>>23)&255)==0||((r>>23)&255)==255)return int(i)+1;
  bool done=false;
  for(int iteration=0;iteration<4;++iteration){
   int upper=midpoint_cmp(u,r,r+1);if(upper==9)return int(i)+1;
   if(upper<0||(upper==0&&(r&1))){++r;continue;}
   int lower=midpoint_cmp(u,r-1,r);if(lower==9)return int(i)+1;
   if(lower>0||(lower==0&&(r&1))){--r;continue;}
   done=true;break;
  }
  if(!done)return int(i)+1;y[i]=value(r);
 }
 return 0;
}

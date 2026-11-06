// DIAGNOSTIC ONLY: FP64 temporary tests grouped exact-sum hypotheses.
// This is not the model implementation or target FP64 support.
#include <cstdint>
#include <cstring>
#include <cmath>
#include <algorithm>
static float bf(uint16_t a){uint32_t u=uint32_t(a)<<16;float x;memcpy(&x,&u,4);return x;}
extern "C" int grouped(const uint16_t*x,const uint16_t*w,float*y,int M,int N,int K,int group,int split,int mode){
 for(int m=0;m<M;++m)for(int n=0;n<N;++n){float total=0;bool first=true;
  for(int k0=0;k0<K;k0+=split){float s=0;int end=std::min(K,k0+split);
   for(int k=k0;k<end;k+=group){double exact=double(s);for(int j=k;j<std::min(k+group,end);++j)exact+=double(bf(x[m*K+j]))*double(bf(w[n*K+j]));float r=float(exact);if(mode==1&&std::abs(double(r))>std::abs(exact))r=std::nextafter(r,0.0f);s=r;}
   if(first){total=s;first=false;}else total=total+s;
  }y[m*N+n]=total;
 }return 0;
}

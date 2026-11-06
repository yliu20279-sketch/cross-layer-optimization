#include <cstdint>
#include <cstring>
#include <algorithm>
static inline float decode(uint16_t v){uint32_t u=uint32_t(v)<<16;float x;std::memcpy(&x,&u,4);return x;}
extern "C" int source_gemm(const uint16_t*x,const uint16_t*w,float*y,int M,int N,int K){
 if(M<1||N<1||K<1||K%64)return -1;
 if(M==1){
  for(int n=0;n<N;++n){float s[64]={};for(int k=0;k<K;++k){float p=decode(x[k])*decode(w[n*K+k]);s[k%64]=s[k%64]+p;}for(int o=32;o;o/=2)for(int i=0;i<o;++i)s[i]=s[i]+s[i+o];y[n]=s[0];}
 }else{
  const int bk=K<=384?K:(K<1536?(K+1)/2:768);
  for(int m=0;m<M;++m)for(int n=0;n<N;++n){float total=0;bool first=true;for(int k0=0;k0<K;k0+=bk){float s=0;int end=std::min(K,k0+bk);for(int k=k0;k<end;k+=2){if(k+1<end){float p=decode(x[m*K+k+1])*decode(w[n*K+k+1]);s=s+p;}float p=decode(x[m*K+k])*decode(w[n*K+k]);s=s+p;}if(first){total=s;first=false;}else total=total+s;}y[m*N+n]=total;}
 }
 return 0;
}

#include <cstdint>
#include <cstring>
#include <algorithm>
static float bf(uint16_t a){uint32_t u=uint32_t(a)<<16;float x;memcpy(&x,&u,4);return x;}
extern "C" int candidate(const uint16_t*x,const uint16_t*w,float*y,int M,int N,int K,int lanes,int block,int order,int tree){
 if(lanes<1||lanes>64||block<1)return -1;
 for(int m=0;m<M;++m)for(int n=0;n<N;++n){float total=0;bool first=true;
  for(int start=0;start<K;start+=block){float s[64]={};int end=std::min(K,start+block);
   for(int i=start;i<end;++i){int k=i;if(order==1){int t=i-start;k=start+(t^1);if(k>=end)k=i;}else if(order==2)k=end-1-(i-start);
    float p=bf(x[m*K+k])*bf(w[n*K+k]);s[(i-start)%lanes]=s[(i-start)%lanes]+p;
   }
   float part=0;if(tree){for(int o=lanes/2;o;o/=2)for(int i=0;i<o;++i)s[i]=s[i]+s[i+o];part=s[0];}else{part=s[0];for(int i=1;i<lanes;++i)part=part+s[i];}
   if(first){total=part;first=false;}else total=total+part;
  }y[m*N+n]=total;
 }return 0;
}

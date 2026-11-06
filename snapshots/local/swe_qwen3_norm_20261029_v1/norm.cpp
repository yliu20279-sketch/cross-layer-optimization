#include <cmath>
extern "C" void inverse(const float*x,float*y,int n){for(int i=0;i<n;++i)y[i]=1.0f/std::sqrt(x[i]);}
extern "C" void mean(const float*x,float*y,int M,int K,int lanes,int mode){for(int m=0;m<M;++m){float s[64]={};for(int k=0;k<K;++k)s[k%lanes]+=x[m*K+k];float v=0;if(mode==0){v=s[0];for(int i=1;i<lanes;++i)v+=s[i];}else{for(int n=lanes/2;n;n/=2)for(int i=0;i<n;++i)s[i]+=s[i+n];v=s[0];}y[m]=v/float(K);}}

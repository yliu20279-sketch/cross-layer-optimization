#include <immintrin.h>
#include <cmath>
#include <algorithm>
extern "C" __m512 Sleef_expf16_u10avx512f(__m512);
extern "C" int sm(const float*x,float*y,float*stats,float*ex,int M,int K){if(K<1)return -1;for(int m=0;m<M;++m){const float*a=x+m*K;float*out=y+m*K;float max=a[0];for(int k=0;k<K;++k){if(!std::isfinite(a[k]))return -2;max=std::max(max,a[k]);}for(int k=0;k<K;k+=16){float t[16]={};for(int j=0;j<std::min(16,K-k);++j)t[j]=a[k+j]-max;__m512 e=Sleef_expf16_u10avx512f(_mm512_loadu_ps(t));_mm512_storeu_ps(t,e);for(int j=0;j<std::min(16,K-k);++j)out[k+j]=t[j];}float lane[16]={};float sum;if(K<16){sum=out[0];for(int k=1;k<K;++k)sum+=out[k];}else{for(int j=0;j<16;++j)lane[j]=out[j];for(int k=16;k<K;++k)lane[k%16]+=out[k];for(int o=8;o;o/=2)for(int j=0;j<o;++j)lane[j]+=lane[j+o];sum=lane[0];}float inv=1.0f/sum;stats[m]=max;stats[M+m]=sum;stats[2*M+m]=inv;for(int k=0;k<K;++k){ex[m*K+k]=out[k];out[k]*=inv;}}return 0;}

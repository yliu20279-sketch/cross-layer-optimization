#include <immintrin.h>
#include <cmath>
#include <algorithm>
extern "C" __m256 Sleef_expf8_u10avx2(__m256);
extern "C" int sm(const float*x,float*y,float*stats,float*ex,int M,int K){if(K<1)return -1;for(int m=0;m<M;++m){const float*a=x+m*K;float*out=y+m*K;float max=a[0];for(int k=0;k<K;++k){if(!std::isfinite(a[k]))return -2;max=std::max(max,a[k]);}for(int k=0;k<K;k+=8){float t[8]={};for(int j=0;j<std::min(8,K-k);++j)t[j]=a[k+j]-max;__m256 e=Sleef_expf8_u10avx2(_mm256_loadu_ps(t));_mm256_storeu_ps(t,e);for(int j=0;j<std::min(8,K-k);++j)out[k+j]=t[j];}float lane[8]={};float sum;if(K<8){sum=out[0];for(int k=1;k<K;++k)sum+=out[k];}else{for(int j=0;j<8;++j)lane[j]=out[j];for(int k=8;k<K;++k)lane[k%8]+=out[k];for(int o=4;o;o/=2)for(int j=0;j<o;++j)lane[j]+=lane[j+o];sum=lane[0];}float inv=1.0f/sum;stats[m]=max;stats[M+m]=sum;stats[2*M+m]=inv;for(int k=0;k<K;++k){ex[m*K+k]=out[k];out[k]*=inv;}}return 0;}

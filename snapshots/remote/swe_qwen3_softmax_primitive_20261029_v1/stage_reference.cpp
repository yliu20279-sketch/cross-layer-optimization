#include <immintrin.h>
#include <algorithm>
extern "C" __m512 Sleef_expf16_u10avx512f(__m512);
extern "C" void source_exp16(const float*x,float*y,int M,int K){for(int m=0;m<M;++m)for(int k=0;k<K;k+=16){float v[16]={};int n=std::min(16,K-k);for(int j=0;j<n;++j)v[j]=x[m*K+k+j];_mm512_storeu_ps(v,Sleef_expf16_u10avx512f(_mm512_loadu_ps(v)));for(int j=0;j<n;++j)y[m*K+k+j]=v[j];}}

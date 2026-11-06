
#include <cmath>
#include <cstring>
#include <algorithm>

#include "tf32_fda.h"
static void split(float x,float &hi,float &lo){uint32_t u;memcpy(&u,&x,4);u&=~8191u;memcpy(&hi,&u,4);lo=x-hi;memcpy(&u,&lo,4);u=(u+4096u)&~8191u;memcpy(&lo,&u,4);}
static float dot(float acc,const float*a,const float*b,int n,int stride){
 float total=acc;acc=0;for(int k=0;k<n;k+=8){float ah[8]={0},al[8]={0},bh[8]={0},bl[8]={0};for(int j=0;j<8&&k+j<n;j++){split(a[k+j],ah[j],al[j]);split(b[(k+j)*stride],bh[j],bl[j]);}acc=hw_block_fma(acc,al,bh,8);acc=hw_block_fma(acc,ah,bl,8);acc=hw_block_fma(acc,ah,bh,8);if(k%32==0){total+=acc;acc=0;}}return total+acc;}
extern "C" void score_tf(const float*q,const float*k,float*s,int M,int N,int D){

#pragma omp parallel for num_threads(16)
for(int i=0;i<M;i++)for(int j=0;j<N;j++){float a=dot(0,q+i*D,k+j*D,D,1);s[i*N+j]=a;}}
static float ex(float x,const float*t){unsigned u;memcpy(&u,&x,4);return t[u];}
extern "C" void attn_tf(const float*s,const float*v,float*y,const float*t,int M,int N,int D,int lanes,int ln,int mode){
float scale=(float)(1.0/std::sqrt((double)D))*1.4426950408889634074f;

#pragma omp parallel for num_threads(16)
for(int i=0;i<M;i++){float max=-INFINITY,den=0,out[512]={0};
for(int b=0;b<N;b+=128){float a[128]={0},p[128]={0},mx=max;
for(int j=0;j<128&&b+j<N;j++){a[j]=(s[i*N+b+j]*(float)(1.0/std::sqrt((double)D)))*1.4426950408889634074f;mx=std::max(mx,a[j]);}
float res=max<mx?ex(max-mx,t):1.f;max=mx;den*=res;
for(int j=0;j<128&&b+j<N;j++)p[j]=ex(a[j]-max,t);
for(int w=0;w<4;w++){float sums[32]={0};for(int l=0;l<lanes;l++)for(int z=0;z<32;z+=lanes*ln)for(int n=0;n<ln;n++){int j=w*32+z+l*ln+n;if(j<(w+1)*32)sums[l]+=p[j];}
for(int bit=1;bit<lanes;bit*=2){float prev[32];memcpy(prev,sums,sizeof sums);for(int l=0;l<lanes;l++)sums[l]=prev[l]+prev[l^bit];}den+=sums[0];}
for(int d=0;d<D;d++){float val=dot(0,p,v+b*D+d,std::min(128,N-b),D);
if(b==0)out[d]=b+128>=N?(1.f/den)*val:val;else if(b+128>=N){float alpha=1.f/den;out[d]=std::fma(alpha,val,(alpha*res)*out[d]);}else out[d]=mode?std::fma(res,out[d],val):val+res*out[d];}
}for(int d=0;d<D;d++)y[i*D+d]=out[d];}}

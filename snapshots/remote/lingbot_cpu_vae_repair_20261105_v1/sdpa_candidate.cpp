
#include <cmath>
#include <cstring>
#include <algorithm>
extern "C" void scores(const float*q,const float*k,float*s,int M,int N,int D){
for(int i=0;i<M;i++)for(int j=0;j<N;j++){float a=0;for(int d=0;d<D;d++)a=std::fma(q[i*D+d],k[j*D+d],a);s[i*N+j]=a;}}
static float ex(float x,const float*t){unsigned u;memcpy(&u,&x,4);return t[u];}
extern "C" void attn(const float*s,const float*v,float*y,const float*t,int M,int N,int D,int lanes,int ln,int mode){
float scale=(float)(1.0/std::sqrt((double)D))*1.4426950408889634074f;
for(int i=0;i<M;i++){float max=-INFINITY,den=0,out[512]={0};
for(int b=0;b<N;b+=128){float a[128]={0},p[128]={0},mx=max;
for(int j=0;j<128&&b+j<N;j++){a[j]=(s[i*N+b+j]*(float)(1.0/std::sqrt((double)D)))*1.4426950408889634074f;mx=std::max(mx,a[j]);}
float res=max<mx?ex(max-mx,t):1.f;max=mx;den*=res;
for(int j=0;j<128&&b+j<N;j++)p[j]=ex(a[j]-max,t);
for(int w=0;w<4;w++){float sums[32]={0};for(int l=0;l<lanes;l++)for(int z=0;z<32;z+=lanes*ln)for(int n=0;n<ln;n++){int j=w*32+z+l*ln+n;if(j<(w+1)*32)sums[l]+=p[j];}
for(int bit=1;bit<lanes;bit*=2){float prev[32];memcpy(prev,sums,sizeof sums);for(int l=0;l<lanes;l++)sums[l]=prev[l]+prev[l^bit];}den+=sums[0];}
for(int d=0;d<D;d++){float val=0;for(int j=0;j<128&&b+j<N;j++)val=std::fma(p[j],v[(b+j)*D+d],val);
if(b==0)out[d]=b+128>=N?val/den:val;else if(b+128>=N){float alpha=1.f/den;out[d]=std::fma(alpha,val,(alpha*res)*out[d]);}else out[d]=mode?std::fma(res,out[d],val):val+res*out[d];}
}for(int d=0;d<D;d++)y[i*D+d]=out[d];}}

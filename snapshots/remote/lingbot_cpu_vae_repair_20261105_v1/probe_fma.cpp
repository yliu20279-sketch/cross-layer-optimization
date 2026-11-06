
#include <cmath>
#include <cstdint>
#include <cstring>
#include <algorithm>
extern "C" void probe(const float*x,const float*w,const float*b,const int*points,int count,float*out){
 int perms[6][3]={{0,1,2},{0,2,1},{1,0,2},{1,2,0},{2,0,1},{2,1,0}};
 int variant=0;
 for(int p=0;p<6;p++)for(int streams: {1,2,4,8})for(int biasfirst=0;biasfirst<2;biasfirst++)for(int fused=0;fused<2;fused++){
  for(int j=0;j<count;j++){
   int oc=points[j*3],h=points[j*3+1],s=points[j*3+2];float acc[8]={0};
   if(biasfirst)acc[0]=b[oc];
   int size[3]={16,3,3},idx[3],k=0;
   for(int a=0;a<size[perms[p][0]];a++)for(int bb=0;bb<size[perms[p][1]];bb++)for(int c=0;c<size[perms[p][2]];c++){
    idx[perms[p][0]]=a;idx[perms[p][1]]=bb;idx[perms[p][2]]=c;
    int ic=idx[0],r=idx[1],ss=idx[2],yy=h+r-1,xx=s+ss-1;
    float v=(yy<0||yy>=60||xx<0||xx>=104)?0.f:x[(ic*60+yy)*104+xx];
    float weight=w[(((oc*16+ic)*3+2)*3+r)*3+ss];
    int z=k++%streams;
    if(fused)acc[z]=std::fma(v,weight,acc[z]);else{volatile float mul=v*weight;acc[z]=acc[z]+mul;}
   }
   float sum=acc[0];for(int i=1;i<streams;i++)sum=sum+acc[i];
   if(!biasfirst)sum=sum+b[oc];
   out[variant*count+j]=sum;
  }
  variant++;
 }
}

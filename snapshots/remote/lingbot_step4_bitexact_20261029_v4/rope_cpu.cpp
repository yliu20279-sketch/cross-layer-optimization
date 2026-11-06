#include <cmath>
extern "C" int rope_cpu(const float*x,const float*f,float*y,int M,int mode){
 for(int m=0;m<M;m++)for(int h=0;h<16;h++)for(int d=0;d<64;d++){
  int pos=m*2048+h*128+2*d;float a=x[pos],b=x[pos+1],c=f[m*128+2*d],s=f[m*128+2*d+1];
  if(mode==0){y[pos]=a*c-b*s;y[pos+1]=a*s+b*c;}
  if(mode==1){y[pos]=std::fmaf(-b,s,a*c);y[pos+1]=std::fmaf(b,c,a*s);}
  if(mode==2){y[pos]=std::fmaf(a,c,-b*s);y[pos+1]=std::fmaf(a,s,b*c);}
 }return 0;
}


#include <immintrin.h>
#include <cmath>
#include <algorithm>
#include <vector>
extern "C" void conv(const float*x,const float*w,const float*b,float*y,int C,int D,int H,int W,int O,int KD,int KH,int KW){
 int OD=D-KD+1,OH=H-KH+1,OW=W-KW+1;
 std::vector<unsigned char> nonzero(C*D,0);
 for(int c=0;c<C;c++)for(int d=0;d<D;d++)for(int j=0;j<H*W;j++)if(x[((long)c*D+d)*H*W+j]!=0.f){nonzero[c*D+d]=1;break;}
 #pragma omp parallel for collapse(2) num_threads(4)
 for(int o=0;o<O;o++)for(int row=0;row<OD*OH;row++){
  int dt=row/OH,hh=row%OH;
  for(int xx=0;xx<OW;xx+=8){
   int tail=std::min(8,OW-xx);__m256 sum=_mm256_setzero_ps();
   for(int c=0;c<C;c++)for(int kd=0;kd<KD;kd++){
    if(!nonzero[c*D+dt+kd])continue;
    for(int kh=0;kh<KH;kh++)for(int kw=0;kw<KW;kw++){
     const float*p=x+(((long)c*D+dt+kd)*H+hh+kh)*W+xx+kw;
     __m256 a;
     if(tail==8)a=_mm256_loadu_ps(p);
     else{alignas(32) float tmp[8]={0};for(int q=0;q<tail;q++)tmp[q]=p[q];a=_mm256_load_ps(tmp);}
     float v=w[((((long)o*C+c)*KD+kd)*KH+kh)*KW+kw];
     sum=_mm256_fmadd_ps(a,_mm256_set1_ps(v),sum);
    }
   }
   if(b)sum=_mm256_add_ps(sum,_mm256_set1_ps(b[o]));
   float*p=y+(((long)o*OD+dt)*OH+hh)*OW+xx;
   if(tail==8)_mm256_storeu_ps(p,sum);
   else{alignas(32) float tmp[8];_mm256_store_ps(tmp,sum);for(int q=0;q<tail;q++)p[q]=tmp[q];}
  }
 }
}

extern "C" void norm(const float*x,float*y,int C,int P){
 #pragma omp parallel for num_threads(4)
 for(int p=0;p<P;p++){
  float lane[32]={0};
  bool vec=C>128;
  for(int l=0;l<32;l++){
   float part[4]={0};
   if(vec){
    for(int base=l*4;base<C;base+=128)for(int j=0;j<4;j++)if(base+j<C){float v=x[(base+j)*P+p];part[j]=std::fma(v,v,part[j]);}
   }else{
    for(int base=l;base<C;base+=128)for(int j=0;j<4;j++){int c=base+j*32;if(c<C){float v=x[c*P+p];part[j]=std::fma(v,v,part[j]);}}
   }
   lane[l]=((part[0]+part[1])+part[2])+part[3];
  }
  for(int offset=1;offset<32;offset*=2){
   float previous[32];for(int l=0;l<32;l++)previous[l]=lane[l];
   for(int l=0;l+offset<32;l++)lane[l]=previous[l]+previous[l+offset];
  }
  y[p]=std::sqrt(lane[0]);
 }
}

extern "C" void norm_strided(const float*x,float*y,int C,int P){
 #pragma omp parallel for num_threads(4)
 for(int p=0;p<P;p++){float sums[4]={0};for(int lane=0;lane<4;lane++){float a[4]={0};for(int base=lane;base<C;base+=16)for(int j=0;j<4;j++){int c=base+4*j;if(c<C){float v=x[c*P+p];a[j]=std::fma(v,v,a[j]);}}sums[lane]=((a[0]+a[1])+a[2])+a[3];}sums[0]+=sums[2];sums[1]+=sums[3];y[p]=std::sqrt(sums[0]+sums[1]);}}

// Fixed, workload-independent candidate accumulation schedules. FP32 only.
#include <cmath>
extern "C" int router_gemm_model(const float*x,const float*w,float*y,int M,int N,int K,int lanes,int reduction,int fused){
 if(M<1||N<1||K<1||lanes<1||lanes>64||(lanes&(lanes-1)))return -1;
 #pragma omp parallel for
 for(int m=0;m<M;++m)for(int n=0;n<N;++n){
  float a[64]={};
  for(int k=0;k<K;++k){int lane=k&(lanes-1);float xv=x[m*K+k],wv=w[n*K+k];
   if(fused)a[lane]=std::fmaf(xv,wv,a[lane]);else{float p=xv*wv;a[lane]=a[lane]+p;}}
  if(reduction==0){for(int s=lanes/2;s;s/=2)for(int i=0;i<s;++i)a[i]=a[i]+a[i+s];}
  else if(reduction==1){for(int s=1;s<lanes;s*=2)for(int i=0;i<lanes;i+=2*s)a[i]=a[i]+a[i+s];}
  else{for(int i=1;i<lanes;++i)a[0]=a[0]+a[i];}
  y[m*N+n]=a[0];
 }
 return 0;
}

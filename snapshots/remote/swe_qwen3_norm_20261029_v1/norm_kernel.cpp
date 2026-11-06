#include <cmath>
extern "C" void inverse(const float*x,float*y,int n){for(int i=0;i<n;++i)y[i]=1.0f/std::sqrt(x[i]);}
extern "C" void mean(const float*x,float*y,int M,int K,int lanes,int mode){for(int m=0;m<M;++m){float s[64]={};for(int k=0;k<K;++k)s[k%lanes]+=x[m*K+k];float v=0;if(mode==0){v=s[0];for(int i=1;i<lanes;++i)v+=s[i];}else{for(int n=lanes/2;n;n/=2)for(int i=0;i<n;++i)s[i]+=s[i+n];v=s[0];}y[m]=v/float(K);}}

extern "C" void cascade(const float*x,float*y,int M,int K,int width){
 for(int m=0;m<M;++m){float a[4][4][16]={};int size=K/width/4;int power=4;int lg=0;while((1<<lg)<size)++lg;if(lg/4>power)power=lg/4;int step=1<<power;int i=0;
 for(;i+step<=size;){for(int t=0;t<step;++t,++i)for(int g=0;g<4;++g)for(int lane=0;lane<width;++lane)a[0][g][lane]+=x[m*K+(i*4+g)*width+lane];for(int lev=1;lev<4;++lev){for(int g=0;g<4;++g)for(int lane=0;lane<width;++lane){a[lev][g][lane]+=a[lev-1][g][lane];a[lev-1][g][lane]=0;}if(i&((step-1)<<(lev*power)))break;}}
 for(;i<size;++i)for(int g=0;g<4;++g)for(int lane=0;lane<width;++lane)a[0][g][lane]+=x[m*K+(i*4+g)*width+lane];
 for(int lev=1;lev<4;++lev)for(int g=0;g<4;++g)for(int lane=0;lane<width;++lane)a[0][g][lane]+=a[lev][g][lane];
 for(int g=1;g<4;++g)for(int lane=0;lane<width;++lane)a[0][0][lane]+=a[0][g][lane];float out=0;for(int lane=0;lane<width;++lane)out+=a[0][0][lane];y[m]=out/float(K);
 }}

#include <cstdint>
#include <cstring>
#include <vector>
static float dec(uint16_t v){uint32_t u=uint32_t(v)<<16;float f;memcpy(&f,&u,4);return f;}
static uint16_t enc(float x){uint32_t u;memcpy(&u,&x,4);return uint16_t((u+0x7fff+((u>>16)&1))>>16);}
extern "C" int rms(const uint16_t*x,uint16_t*y,float*stats,int M,int K,float eps){if(K!=128&&K!=2048)return -1;std::vector<float>sq(M*K);for(int i=0;i<M*K;++i){float f=dec(x[i]);sq[i]=f*f;}cascade(sq.data(),stats,M,K,8);for(int m=0;m<M;++m){stats[M+m]=stats[m]+eps;stats[2*M+m]=1.0f/std::sqrt(stats[M+m]);for(int k=0;k<K;++k)y[m*K+k]=enc(dec(x[m*K+k])*stats[2*M+m]);}return 0;}

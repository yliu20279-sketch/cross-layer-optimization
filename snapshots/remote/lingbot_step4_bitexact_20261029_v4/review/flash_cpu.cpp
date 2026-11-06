// Own noncausal FlashAttention64 recurrence; integer FDA helper attributed upstream.
#include <vector>
#include <cstring>
struct Parts{std::vector<int8_t>s;std::vector<int16_t>e;std::vector<uint16_t>g;Parts(const float*x,int n):s(n),e(n),g(n){extract_parts(x,n,s.data(),e.data(),g.data());}};
static uint32_t bits(float x){uint32_t u;memcpy(&u,&x,4);return u;}
static float val(uint32_t u){float x;memcpy(&x,&u,4);return x;}
static float rb_cpu(float x){uint32_t u=bits(x);return val((u+0x7fff+((u>>16)&1))&0xffff0000);}
extern "C" int flash_cpu(const float*q,const float*k,const float*v,float*out,int M,int S,const uint32_t*ex2,const uint32_t*rcp,int mode){
 if(M<1||S<1)return -1;
 Parts Q(q,M*2048),K(k,S*2048);std::vector<float>vt(2048*S);
 for(int h=0;h<16;h++)for(int d=0;d<128;d++)for(int s=0;s<S;s++)vt[(h*128+d)*S+s]=v[s*2048+h*128+d];Parts V(vt.data(),2048*S);
 const float scale=0.127517432f;
 #pragma omp parallel for collapse(2) schedule(dynamic)
 for(int m=0;m<M;m++)for(int h=0;h<16;h++){
  float mx=-INFINITY,sum[4]={0},o[128]={0};bool first=true;int qi=m*2048+h*128;
  for(int tile=(S+63)/64-1;tile>=0;tile--){int start=tile*64,n=S-start;if(n>64)n=64;float scores[64],p[64];
   for(int j=0;j<64;j++){if(j>=n){scores[j]=-INFINITY;continue;}int ki=(start+j)*2048+h*128;float acc=0;
    for(int a=0;a<128;a+=16)acc=hw_block_fma_pre(acc,&Q.s[qi+a],&Q.e[qi+a],&Q.g[qi+a],&K.s[ki+a],&K.e[ki+a],&K.g[ki+a],16);scores[j]=acc;}
   float newmx=mx;for(int j=0;j<64;j++)newmx=fmaxf(newmx,scores[j]);float rescale=first?0:val(ex2[bits((mx-newmx)*scale)]);float mscaled=newmx*scale;
   for(int j=0;j<64;j++)p[j]=val(ex2[bits(fmaf(scores[j],scale,-mscaled))]);
   for(int t=0;t<4;t++){int c=2*t;float a;if(first)a=p[c];else a=(mode&1)?sum[t]*rescale+p[c]:fmaf(sum[t],rescale,p[c]);a=a+p[c+1];for(int atom=1;atom<8;atom++){a=a+p[atom*8+c];a=a+p[atom*8+c+1];}sum[t]=a;}
   if(!first)for(int d=0;d<128;d++)o[d]=o[d]*rescale;
   for(int j=0;j<64;j++)p[j]=rb_cpu(p[j]);Parts P(p,64);
   for(int d=0;d<128;d++){int vi=(h*128+d)*S+start;for(int a=0;a<n;a+=16){int count=n-a;if(count>16)count=16;o[d]=hw_block_fma_pre(o[d],&P.s[a],&P.e[a],&P.g[a],&V.s[vi+a],&V.e[vi+a],&V.g[vi+a],count);}}
   mx=newmx;first=false;
  }
  float total=(sum[0]+sum[2])+(sum[1]+sum[3]);uint32_t u=bits(total),e=(u>>23)&255;float inv=(mode&2)?1.0f/total:val(rcp[u&0x7fffff]-(e-127)*0x800000u);
  for(int d=0;d<128;d++)out[m*2048+h*128+d]=rb_cpu(o[d]*inv);
 }
 return 0;
}

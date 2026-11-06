#include "lifetime_allocator.h"
#pragma once
#include <cstring>
#include <cmath>
#include <utility>
#include <set>
#include "npusim_tensor_codec.h"
extern "C" int rms(const std::uint16_t*,std::uint16_t*,float*,int,int,float);
static const float* exp_table=nullptr;static const std::uint16_t*silu_table=nullptr;
static std::vector<std::vector<char>> positional_constants;
static float dec(std::uint16_t b){return NPUSim::bf16BitsToFloat(b);}static std::uint16_t enc(float f){return NPUSim::floatToBf16Bits(f);}
static void service(const std::uint64_t*h,const std::vector<char>&in,std::vector<char>&out){
 using U=std::uint64_t;U kind=h[1],a=h[4],b=h[5],c=h[6];auto bf=(const std::uint16_t*)in.data();auto fp=(const float*)in.data();auto yf=(float*)out.data();auto yb=(std::uint16_t*)out.data();
 if(kind==1){if(in.size()!=a*2||out.size()!=a*4)throw std::runtime_error("decode sizes");for(U i=0;i<a;i++)yf[i]=dec(bf[i]);}
 else if(kind==2){if(in.size()!=a*4||out.size()!=a*2)throw std::runtime_error("encode sizes");for(U i=0;i<a;i++)yb[i]=enc(fp[i]);}
 else if(kind==3){if(in.size()!=a*b*2||out.size()!=a*b*2+a*12)throw std::runtime_error("norm sizes");std::uint32_t bits=c;float eps;memcpy(&eps,&bits,4);if(rms(bf,yb,(float*)(out.data()+a*b*2),a,b,eps))throw std::runtime_error("norm geometry");}
 else if(kind==4){if(in.size()!=2*a||out.size()!=2*a)throw std::runtime_error("silu sizes");for(U i=0;i<a;i++)yb[i]=silu_table[bf[i]];}
 else if(kind==5){if(in.size()!=a*b*(c?2:4)||out.size()!=a*b*4)throw std::runtime_error("softmax sizes");if(b!=19&&b!=20&&b!=128)throw std::runtime_error("softmax geometry");for(U m=0;m<a;m++){
  auto value=[&](U k){return c?dec(bf[m*b+k]):fp[m*b+k];};float max=value(0);for(U k=0;k<b;k++){float v=value(k);if(!std::isfinite(v))throw std::runtime_error("softmax input");max=std::max(max,v);}float*outrow=yf+m*b;
  for(U k=0;k<b;k++){float d=value(k)-max;std::uint32_t bits;memcpy(&bits,&d,4);outrow[k]=exp_table[bits];}
  float sum;if(b<16){sum=outrow[0];for(U k=1;k<b;k++)sum+=outrow[k];}else{float lane[16];for(int k=0;k<16;k++)lane[k]=outrow[k];for(U k=16;k<b;k++)lane[k%16]+=outrow[k];for(int half=8;half;half/=2)for(int k=0;k<half;k++)lane[k]+=lane[k+half];sum=lane[0];}float inv=1.0f/sum;for(U k=0;k<b;k++)outrow[k]*=inv;
 }}
 else if(kind==6){if(in.size()!=a*128*4||out.size()!=a*8*12)throw std::runtime_error("topk size");auto ids=(std::int64_t*)(out.data()+a*8*4);for(U m=0;m<a;m++){std::vector<std::pair<float,std::int64_t>>q(128);for(int i=0;i<128;i++){if(!std::isfinite(fp[m*128+i]))throw std::runtime_error("topk nonfinite");q[i]={fp[m*128+i],i};}auto cmp=[](const auto&a,const auto&b){return a.first>b.first;};std::nth_element(q.begin(),q.begin()+7,q.end(),cmp);std::sort(q.begin(),q.begin()+7,cmp);for(int i=0;i<8;i++){yf[m*8+i]=q[i].first;ids[m*8+i]=q[i].second;}}}
 else if(kind==7){if(in.size()!=a*8*4||out.size()!=a*8*4)throw std::runtime_error("route norm size");for(U m=0;m<a;m++){float sum=0;for(int i=0;i<8;i++)sum+=fp[m*8+i];for(int i=0;i<8;i++)yf[m*8+i]=fp[m*8+i]/sum;}}
 else if(kind==8){if(in.size()!=a*b+c*8||out.size()!=c*b)throw std::runtime_error("gather size");auto ids=(const std::int64_t*)(in.data()+a*b);for(U i=0;i<c;i++){auto id=ids[i];if(id<-(std::int64_t)a||id>=(std::int64_t)a)throw std::runtime_error("gather bounds");if(id<0)id+=a;memcpy(out.data()+i*b,in.data()+id*b,b);}}
 else if(kind==9){if(in.size()!=a*b*2+c*8+c*b*2||out.size()!=a*b*2)throw std::runtime_error("index_add size");memcpy(out.data(),in.data(),out.size());auto ids=(const std::int64_t*)(in.data()+a*b*2);auto updates=(const std::uint16_t*)(in.data()+a*b*2+c*8);std::set<std::int64_t>seen;for(U i=0;i<c;i++){auto id=ids[i];if(id<0||id>=(std::int64_t)a||!seen.insert(id).second)throw std::runtime_error("unsupported duplicate/index_add bounds");for(U k=0;k<b;k++)yb[id*b+k]=enc(dec(yb[id*b+k])+dec(updates[i*b+k]));}}
 else if(kind==11){if(in.size()!=a*8*8||out.size()!=128*8+a*8*16)throw std::runtime_error("dispatch metadata size");auto ids=(const std::int64_t*)in.data();auto counts=(U*)out.data();auto tokens=(U*)(out.data()+128*8);auto slots=tokens+a*8;U n=0;for(U e=0;e<128;e++){counts[e]=0;for(U s=0;s<8;s++)for(U t=0;t<a;t++){auto id=ids[t*8+s];if(id<0||id>=128)throw std::runtime_error("expert id");if(id==(std::int64_t)e){tokens[n]=t;slots[n++]=s;counts[e]++;}}}if(n!=a*8)throw std::runtime_error("dispatch conservation");}
 else if(kind==12){if(in.size()!=a*2||out.size()!=a*2)throw std::runtime_error("scale size");std::uint32_t bits=b;float scale;memcpy(&scale,&bits,4);for(U i=0;i<a;i++)yb[i]=enc(dec(bf[i])*scale);}
 else if(kind==13){if(a!=4||in.size()!=a*(b+c)*128*2||out.size()!=in.size())throw std::runtime_error("KV concat size");U oldbytes=a*b*128*2;for(U head=0;head<a;head++){memcpy(out.data()+head*(b+c)*256,in.data()+head*b*256,b*256);memcpy(out.data()+(head*(b+c)+b)*256,in.data()+oldbytes+head*c*256,c*256);}}
 else if(kind==14){if(in.size()!=c*8||out.size()!=8)throw std::runtime_error("KV positions size");auto pos=(const std::int64_t*)in.data();for(U i=0;i<c;i++)if(pos[i]!=(std::int64_t)(b+i))throw std::runtime_error("KV positions sequence");std::uint64_t done=b+c;memcpy(out.data(),&done,8);}
 else if(kind==15){if(b!=128||in.size()!=a*2||out.size()!=in.size()||a%128)throw std::runtime_error("rotate size");for(U row=0;row<a;row+=128)for(U k=0;k<64;k++){yb[row+k]=bf[row+64+k]^0x8000;yb[row+64+k]=bf[row+k];}}
 else if(kind==16){if(in.size()!=a*c||out.size()!=a*b*c)throw std::runtime_error("repeat KV size");for(U head=0;head<a;head++)for(U n=0;n<b;n++)memcpy(out.data()+(head*b+n)*c,in.data()+head*c,c);}
 else if(kind==17){if(!in.empty()||out.size()!=a*b*2||c+a!=b)throw std::runtime_error("causal mask shape");for(U q=0;q<a;q++)for(U k=0;k<b;k++)yb[q*b+k]=k<=c+q?0:0xff7f;}
 else if(kind==18){if(!in.empty())throw std::runtime_error("zero input");memset(out.data(),0,out.size());}
 else if(kind==19){if(in.size()!=out.size()||in.size()!=a*b)throw std::runtime_error("stack size");memcpy(out.data(),in.data(),in.size());}
 else if(kind==20){if(in.size()!=a*16||out.size()!=a*8)throw std::runtime_error("route offset size");auto v=(const std::int64_t*)in.data();auto ids=(std::int64_t*)out.data();for(U i=0;i<a;i++){if(v[i]<0||v[i]>=19||v[a+i]<0||v[a+i]>=8)throw std::runtime_error("route offset bounds");ids[i]=v[i]*8+v[a+i];}}
 else if(kind==21){if(!in.empty()||a>=positional_constants.size()||positional_constants[a].size()!=out.size())throw std::runtime_error("positional input contract");memcpy(out.data(),positional_constants[a].data(),out.size());}
 else if(kind==22){if(c<1||c>8||in.size()!=a*b+(1+2*c)*8||!b||out.size()%b)throw std::runtime_error("strided descriptor size");std::int64_t meta[17];memcpy(meta,in.data()+a*b,(1+2*c)*8);U count=1;for(U d=0;d<c;d++){if(meta[1+d]<1||meta[1+c+d]<0)throw std::runtime_error("strided shape");count*=meta[1+d];}if(count*b!=out.size())throw std::runtime_error("strided output size");for(U i=0;i<count;i++){U rem=i;std::int64_t idx=meta[0];for(int d=int(c)-1;d>=0;d--){idx+=(rem%meta[1+d])*meta[1+c+d];rem/=meta[1+d];}if(idx<0||U(idx)>=a)throw std::runtime_error("strided bounds");memcpy(out.data()+i*b,in.data()+idx*b,b);}}
 else if(kind==24){if(!in.empty()||out.size()!=32)throw std::runtime_error("allocation descriptor");lifetime_allocator.allocate(a,b,c,(U*)out.data());}
 else if(kind==25){if(!in.empty()||out.size()!=32)throw std::runtime_error("release descriptor");lifetime_allocator.read_complete(a,b,c,(U*)out.data());}
 else if(kind==26){if(!in.empty()||out.size()!=32+16*a)throw std::runtime_error("barrier descriptor");lifetime_allocator.barrier(a,(U*)out.data());}
 else if(kind==27||kind==28){if(!in.empty()||out.size()!=32)throw std::runtime_error("owner descriptor");lifetime_allocator.owner(a,b,kind==27,(U*)out.data());}
 else if(kind==29){if(!in.empty()||out.size()!=32)throw std::runtime_error("inspect descriptor");lifetime_allocator.inspect((U*)out.data());}
 else throw std::runtime_error("unknown CPU software service");
}

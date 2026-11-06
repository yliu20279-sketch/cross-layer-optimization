// Independent finite-domain software realization of the pinned router contract.
// CUDA algorithm provenance is recorded separately; this is host x86 code.
#include "/mnt/sda1/h3240101068/olmoearth_v3_6_integration_20261025_v1/source/NPUSim/npusim_tensor_codec.h"
#include <cmath>
#include <cstdint>
#include <limits>
#include <utility>
namespace {
bool pick(const float* p,std::int64_t* ids,float* selected) {
 float best[8];for(float& b:best)b=-std::numeric_limits<float>::infinity();
 for(int e=0;e<128;++e) {
  if(!std::isfinite(p[e]) || p[e]<0 || (p[e]==0 && std::signbit(p[e])))return false;
  float candidate=p[e];
  for(int j=0;j<8;++j)if(candidate>best[j])std::swap(candidate,best[j]);
 }
 const float boundary=best[7];float keys[32]={};std::int64_t tags[32]={};bool valid[32]={};int count=0;
 // Source threshold gather: strict winners first, then first encountered equals.
 for(int e=0;e<128;++e)if(p[e]>boundary){keys[count]=p[e];tags[count]=e;valid[count++]=true;}
 for(int e=0;e<128 && count<8;++e)if(p[e]==boundary){keys[count]=p[e];tags[count]=e;valid[count++]=true;}
 if(count!=8)return false;
 auto exchange=[&](int left,int right,bool direction) {
  const bool relation=(valid[left] && keys[left]>keys[right]) || !valid[right];
  if(relation==direction){std::swap(keys[left],keys[right]);std::swap(tags[left],tags[right]);std::swap(valid[left],valid[right]);}
 };
 //32-wire schedule, including invalid lanes; equal-value exchanges matter.
 for(int width=2;width<32;width*=2)
  for(int gap=width/2;gap;gap/=2)
   for(int lane=0;lane<16;++lane){int left=2*lane-(lane&(gap-1));exchange(left,left+gap,(lane&(width/2))!=0);}
 for(int gap=16;gap;gap/=2)
  for(int lane=0;lane<16;++lane){int left=2*lane-(lane&(gap-1));exchange(left,left+gap,false);}
 for(int j=0;j<8;++j){if(!valid[j])return false;ids[j]=tags[j];selected[j]=keys[j];}
 return true;
}
bool normalize(const float* selected,std::uint16_t* weight) {
 float temp[8];for(int i=0;i<8;++i)temp[i]=selected[i];
 for(int gap=4;gap;gap/=2)for(int i=0;i<gap;++i)temp[i]=temp[i]+temp[i+gap];
 float sum=temp[0];if(!(sum>0) || !std::isfinite(sum))return false;
 for(int i=0;i<8;++i)weight[i]=NPUSim::floatToBf16Bits(selected[i]/sum);
 return true;
}
}
extern "C" {
int select_route128(const float* probability,std::int64_t* ids,std::uint16_t* weights,std::size_t rows) {
 for(std::size_t row=0;row<rows;++row){float selected[8];if(!pick(probability+128*row,ids+8*row,selected) || !normalize(selected,weights+8*row))return int(row)+1;}
 return 0;
}
int full_route128(const std::uint16_t* logits,float* probability,std::int64_t* ids,std::uint16_t* weights,std::size_t rows) {
 for(std::size_t row=0;row<rows;++row) {
  float values[128];float maximum=-std::numeric_limits<float>::infinity();
  for(int e=0;e<128;++e){float v=NPUSim::bf16BitsToFloat(logits[row*128+e]);if(!std::isfinite(v))return int(row)+1;values[e]=v;if(v>maximum)maximum=v;}
  float sum=0;
  for(int e=0;e<128;++e){float v=std::exp(values[e]-maximum);probability[row*128+e]=v;sum=sum+v;}
  for(int e=0;e<128;++e)probability[row*128+e]=probability[row*128+e]/sum;
 }
 return select_route128(probability,ids,weights,rows);
}
}

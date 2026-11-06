#include <cmath>
#include <algorithm>
#include <cstdint>
extern "C" int identify(const float*x,const float*w,const float*y,int*out){
 // y[pattern,row,expert]; every model-independent pattern has identical input rows.
 int failures=0;
 for(int row=0;row<1;row++)for(int n=0;n<128;n++){
  int p[8]={0,1,2,3,4,5,6,7},count=0;
  do{bool ok=true;for(int t=0;t<16&&ok;t++){float acc=0;for(int i=0;i<8;i++)acc=std::fmaf(x[t*8+p[i]],w[(t*128+n)*8+p[i]],acc);ok=*(uint32_t*)&acc==((uint32_t*)y)[(t*128+row)*128+n];}
   if(ok){for(int i=0;i<8;i++)out[(row*128+n)*9+i]=p[i];count++;}
  }while(std::next_permutation(p,p+8));out[(row*128+n)*9+8]=count;if(!count)failures++;
 }return failures;
}

#include "Vbenes8.h"
#include "verilated.h"
#include <algorithm>
#include <array>
#include <iostream>
int main(int argc,char**argv){
 Verilated::commandArgs(argc,argv);Vbenes8 d;std::array<int,8> p{0,1,2,3,4,5,6,7};int count=0;bool five=argc>1;
 do{
  d.permutation=0;
  for(int i=0;i<8;i++){d.permutation|=p[i]<<(3*i);for(int k=0;k<9;k++)d.din[i][k]=((k+1)*100+i)&(k==8?15u:~0u);}
  d.eval();for(int i=0;i<8;i++)for(int k=0;k<9;k++)if(d.dout[p[i]][k]!=(unsigned((k+1)*100+i)&(k==8?15u:~0u))){
   std::cerr<<"FAIL permutation "<<count<<" input "<<i<<" output "<<p[i]<<'\n';return 1;
  }
  ++count;
 }while(std::next_permutation(p.begin(),five?p.begin()+5:p.end()));
 std::cout<<"PASS "<<count<<" complete 8x8 Beneš permutations, 260 data/control bits\n";
}

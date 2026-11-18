#include "Vwidth_link.h"
#include "verilated.h"
#include <array>
#include <iostream>
#include <stdexcept>
int main(int argc,char**argv){
 Verilated::commandArgs(argc,argv);
 for(int lanes=1;lanes<=4;lanes++){
  Vwidth_link d;d.clk=0;d.reset=1;d.in_valid=0;d.lanes=lanes;d.out_credit=15;
  for(int t=0;t<3;t++){d.eval();d.clk=1;d.eval();d.clk=0;d.eval();}d.reset=0;
  int sent=0,received=0,cycle=0;std::array<bool,256> seen{};
  while(received<256&&cycle<5000){
   d.in_valid=sent<256;for(int k=0;k<8;k++)d.in_flit[k]=unsigned(sent)^unsigned(k*2246822519u);
   d.in_flit[8]=((sent%4)<<2)|3;d.clk=0;d.eval();
   bool accepted=d.in_valid&&((d.in_credit>>(sent%4))&1);
   if(d.out_valid){
    unsigned id=d.out_flit[0];if(id>=256||seen[id])throw std::runtime_error("link duplicate or corrupt ID");
    for(int k=0;k<8;k++)if(d.out_flit[k]!=(id^unsigned(k*2246822519u)))throw std::runtime_error("link payload corruption");
    if(d.out_flit[8]!=((id%4)<<2|3))throw std::runtime_error("link header/tail/VN corruption");
    seen[id]=true;++received;
   }
   d.clk=1;d.eval();d.clk=0;d.eval();if(accepted)++sent;++cycle;
  }
  if(received!=256||cycle>(1024+lanes-1)/lanes+20)throw std::runtime_error("incorrect serialized throughput");
  std::cout<<"PASS "<<lanes<<"x64-bit link, 256 flits in "<<cycle<<" cycles, exact data and VN framing\n";
 }
}

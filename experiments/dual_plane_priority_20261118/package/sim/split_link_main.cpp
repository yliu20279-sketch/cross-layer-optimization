#include "Vsplit_width_link.h"
#include "verilated.h"
#include <array>
#include <iostream>
#include <stdexcept>
int main(int argc,char**argv){
 Verilated::commandArgs(argc,argv);
 for(int global=0;global<=4;global++){
  Vsplit_width_link d;d.clk=0;d.reset=1;d.in_valid=0;d.global_lanes=global;d.out_credit[0]=15;d.out_credit[1]=15;
  for(int t=0;t<3;t++){d.eval();d.clk=1;d.eval();d.clk=0;d.eval();}d.reset=0;
  int sent[2]={0,0},received[2]={0,0},cycle=0;std::array<std::array<bool,256>,2> seen{};
  int target0=global?256:0,target1=global<4?256:0;
  while((received[0]<target0||received[1]<target1)&&cycle<5000){
   d.in_valid=0;
   for(int dom=0;dom<2;dom++){
    if(sent[dom]<(dom?target1:target0))d.in_valid|=1<<dom;
    for(int k=0;k<8;k++)d.in_flit[dom][k]=unsigned(sent[dom])^unsigned(dom<<24)^unsigned(k*2246822519u);
    d.in_flit[dom][8]=((sent[dom]%4)<<2)|3;
   }
   d.clk=0;d.eval();bool accept[2];
   for(int dom=0;dom<2;dom++){
    accept[dom]=((d.in_valid>>dom)&1)&&((d.in_credit[dom]>>(sent[dom]%4))&1);
    if((d.out_valid>>dom)&1){
     unsigned id=d.out_flit[dom][0]^unsigned(dom<<24);if(id>=256||seen[dom][id])throw std::runtime_error("split link duplicate or wrong domain");
     for(int k=0;k<8;k++)if(d.out_flit[dom][k]!=(id^unsigned(dom<<24)^unsigned(k*2246822519u)))throw std::runtime_error("split link payload corruption");
     if(d.out_flit[dom][8]!=((id%4)<<2|3))throw std::runtime_error("split link framing corruption");
     seen[dom][id]=true;received[dom]++;
    }
   }
   d.clk=1;d.eval();d.clk=0;d.eval();for(int dom=0;dom<2;dom++)if(accept[dom])sent[dom]++;++cycle;
  }
  int limit=global==0||global==4?276:std::max((1024+global-1)/global,(1024+3-global)/(4-global))+24;
  if(received[0]!=target0||received[1]!=target1||cycle>limit)throw std::runtime_error("shared physical lane throughput mismatch");
  std::cout<<"PASS shared four-lane link G/L="<<global<<'/'<<4-global<<", delivered "<<received[0]<<'+'<<received[1]<<" flits in "<<cycle<<" cycles\n";
 }
}

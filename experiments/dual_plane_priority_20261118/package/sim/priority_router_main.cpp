#include "Vxy_router.h"
#include "verilated.h"
#include <iostream>
#include <stdexcept>
static void step(Vxy_router& d){d.clk=0;d.eval();d.clk=1;d.eval();d.clk=0;d.eval();}
static void reset(Vxy_router& d){
 d.clk=0;d.reset=1;d.in_valid=0;
 for(int i=0;i<5;i++){d.out_credit[i]=0;for(int k=0;k<9;k++)d.in_flit[i][k]=0;}
 step(d);step(d);d.reset=0;d.eval();
}
static void enqueue(Vxy_router& d,int vn,int dst){
 d.in_valid=1;for(int k=0;k<9;k++)d.in_flit[0][k]=0;
 const int opcode=vn==3?5:vn==2?2:vn==1?1:3;
 d.in_flit[0][7]=(unsigned(opcode)<<28)|(unsigned(dst)<<24);d.in_flit[0][8]=(vn<<2)|3;
 d.eval();if(!(d.in_credit[0]&(1<<vn)))throw std::runtime_error("input blocked");step(d);
}
int main(int argc,char**argv){
 Verilated::commandArgs(argc,argv);Vxy_router d;reset(d);
 for(int vn=0;vn<4;vn++)enqueue(d,vn,0);
 d.in_valid=0;d.out_credit[4]=15;d.eval();
 for(int vn=3;vn>=0;vn--){
  std::cout<<"expected VN "<<vn<<" output valid "<<unsigned(d.out_valid)<<" actual VN "<<(d.out_flit[4][8]>>2)<<std::endl;
  if(!(d.out_valid&16)||((d.out_flit[4][8]>>2)&3)!=unsigned(vn))throw std::runtime_error("fixed class order violated");step(d);
 }
 reset(d);enqueue(d,0,1);enqueue(d,3,0);d.in_valid=0;d.out_credit[0]=15;d.out_credit[4]=15;d.eval();
 if(!(d.out_valid&16)||(d.out_valid&1))throw std::runtime_error("cross-output input priority violated");
 step(d);if(!(d.out_valid&1)||((d.out_flit[0][8]>>2)&3)!=0)throw std::runtime_error("low class failed to resume");
 std::cout<<"PASS fixed class priority and cross-output input conflict"<<std::endl;
}

#include <cstdint>
#include <vector>
#include <fstream>
#include <string>
#include <cstring>
#include <stdexcept>
#include <iostream>
#include "sim_api.h"
extern "C" void extract_parts(const float*,int,int8_t*,int16_t*,uint16_t*);
extern "C" void tc_matmul_opt(const int8_t*,const int16_t*,const uint16_t*,const int8_t*,const int16_t*,const uint16_t*,float*,int,int,int);
extern "C" void tc_block_fma_batch(float*,const float*,const float*,int,int,int);
static inline void marker(unsigned long a){unsigned long cmd=4,b=0;asm volatile("xchg %%bx,%%bx" : "+a"(cmd),"+b"(a),"+c"(b) : : "memory");}
template<class T> std::vector<T> load(const std::string&p){std::ifstream f(p,std::ios::binary|std::ios::ate);auto n=f.tellg();if(n<=0||n%sizeof(T))throw std::runtime_error("bad input "+p);std::vector<T>a(n/sizeof(T));f.seekg(0);f.read((char*)a.data(),n);if(!f)throw std::runtime_error("short input");return a;}
template<class T> void save(const std::string&p,const std::vector<T>&a){std::ofstream f(p,std::ios::binary);f.write((char*)a.data(),a.size()*sizeof(T));}
static float dec(uint16_t b){uint32_t u=(uint32_t)b<<16;float y;std::memcpy(&y,&u,4);return y;}
static uint16_t enc(float a){uint32_t u;std::memcpy(&u,&a,4);if((u&0x7f800000)==0x7f800000)throw std::runtime_error("finite admitted outputs only");return (u+0x7fff+((u>>16)&1))>>16;}
struct Job{std::string label;int N,K,mode;std::vector<uint16_t>xb,wb,bias,gold;std::vector<float>x,w,out,carry,expected;std::vector<uint16_t>bits;std::vector<int8_t>xs,ws;std::vector<int16_t>xe,we;std::vector<uint16_t>xg,wg;};
int main(int argc,char**argv){try{std::string R=argv[1];std::vector<Job>jobs;
 for(int i=0;i<3;i++){Job j;j.label=i==0?"K":i==1?"V":"Ocarry";j.N=i==2?2048:128;j.K=i==2?128:2048;j.mode=i==2;j.xb=load<uint16_t>(R+"/"+j.label+"_x.bin");j.wb=load<uint16_t>(R+"/"+j.label+"_w.bin");j.gold=load<uint16_t>(R+"/"+j.label+"_GPU.bin");j.expected=load<float>(R+"/"+j.label+"_F32_reference.bin");if(j.xb.size()!=(size_t)j.K||j.wb.size()!=(size_t)j.N*j.K||j.gold.size()!=(size_t)j.N||j.expected.size()!=(size_t)j.N)throw std::runtime_error("geometry");j.x.resize(j.K);j.w.resize(j.K*j.N);j.out.resize(j.N);j.bits.resize(j.N);j.xs.resize(j.K);j.xe.resize(j.K);j.xg.resize(j.K);j.ws.resize(j.K*j.N);j.we.resize(j.K*j.N);j.wg.resize(j.K*j.N);if(j.mode){j.carry=load<float>(R+"/Ocarry_initial.bin");j.bias=load<uint16_t>(R+"/Ocarry_bias.bin");if(j.carry.size()!=(size_t)j.N||j.bias.size()!=(size_t)j.N)throw std::runtime_error("carry geometry");}jobs.push_back(std::move(j));}
 SimRoiStart();
 for(int i=0;i<3;i++){Job&j=jobs[i];marker(100+i*10);for(int k=0;k<j.K;k++)j.x[k]=dec(j.xb[k]);for(int k=0;k<j.K*j.N;k++)j.w[k]=dec(j.wb[k]);if(j.mode)for(int n=0;n<j.N;n++)j.out[n]=j.carry[n];marker(101+i*10);
  if(!j.mode){extract_parts(j.x.data(),j.K,j.xs.data(),j.xe.data(),j.xg.data());extract_parts(j.w.data(),j.K*j.N,j.ws.data(),j.we.data(),j.wg.data());tc_matmul_opt(j.xs.data(),j.xe.data(),j.xg.data(),j.ws.data(),j.we.data(),j.wg.data(),j.out.data(),1,j.K,j.N);}else{for(int k=0;k<j.K;k+=16)tc_block_fma_batch(j.out.data(),j.x.data()+k,j.w.data()+k*j.N,1,16,j.N);}
  marker(102+i*10);for(int n=0;n<j.N;n++){float a=j.mode?j.out[n]+dec(j.bias[n]):j.out[n];j.bits[n]=enc(a);}marker(103+i*10);
 }
 SimRoiEnd();
 for(auto&j:jobs){save(R+"/"+j.label+"_actual_F32.bin",j.out);save(R+"/"+j.label+"_actual_BF16.bin",j.bits);if(std::memcmp(j.out.data(),j.expected.data(),j.N*4)||std::memcmp(j.bits.data(),j.gold.data(),j.N*2))throw std::runtime_error("bit mismatch "+j.label);}
 std::ofstream(R+"/FUNCTIONAL_PASS.json")<<"{\"state\":\"PASS_PORTABLE_CPU_KV_OCARRY\",\"FP32_elements\":2304,\"BF16_elements\":2304,\"GPU_count\":0,\"scope\":\"one actual query, head0 K/V and head15 O carry, CPU software kernel only\"}";return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}

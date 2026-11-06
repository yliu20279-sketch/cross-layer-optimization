#include <cstdint>
#include <vector>
#include <fstream>
#include <string>
#include <cstring>
#include <stdexcept>
#include <iostream>
#include "sim_api.h"
#include "apis_c.h"
#include <algorithm>
extern "C" void extract_parts(const float*,int,int8_t*,int16_t*,uint16_t*);
extern "C" void tc_matmul_opt(const int8_t*,const int16_t*,const uint16_t*,const int8_t*,const int16_t*,const uint16_t*,float*,int,int,int);
extern "C" void tc_block_fma_batch(float*,const float*,const float*,int,int,int);
static inline void marker(unsigned long a){unsigned long cmd=4,b=0;asm volatile("xchg %%bx,%%bx" : "+a"(cmd),"+b"(a),"+c"(b) : : "memory");}
template<class T> std::vector<T> load(const std::string&p){std::ifstream f(p,std::ios::binary|std::ios::ate);auto n=f.tellg();if(n<=0||n%sizeof(T))throw std::runtime_error("bad input "+p);std::vector<T>a(n/sizeof(T));f.seekg(0);f.read((char*)a.data(),n);if(!f)throw std::runtime_error("short input");return a;}
template<class T> void save(const std::string&p,const std::vector<T>&a){std::ofstream f(p,std::ios::binary);f.write((char*)a.data(),a.size()*sizeof(T));}
static float dec(uint16_t b){uint32_t u=(uint32_t)b<<16;float y;std::memcpy(&y,&u,4);return y;}
static uint16_t enc(float a){uint32_t u;std::memcpy(&u,&a,4);if((u&0x7f800000)==0x7f800000)throw std::runtime_error("finite admitted outputs only");return (u+0x7fff+((u>>16)&1))>>16;}
struct Job{std::string label;int N,K,mode;std::vector<uint16_t>xb,wb,bias,gold;std::vector<float>x,w,out,carry,expected;std::vector<uint16_t>bits;std::vector<int8_t>xs,ws;std::vector<int16_t>xe,we;std::vector<uint16_t>xg,wg;};
static void rx(void*p,size_t n){for(size_t off=0;off<n;off+=65536){auto k=std::min<size_t>(65536,n-off);if(InterChiplet::receiveMessage(0,12,0,4,(char*)p+off,k)<0)throw std::runtime_error("CPU receive");}}
static void tx(void*p,size_t n){for(size_t off=0;off<n;off+=65536){auto k=std::min<size_t>(65536,n-off);if(InterChiplet::sendMessage(0,4,0,12,(char*)p+off,k)<0)throw std::runtime_error("CPU send");}}
int main(int argc,char**argv){try{std::string R=argv[1],base=argv[2];int round=0;{std::ifstream f(base+"/CPU_ROUND");f>>round;}round++;{std::ofstream f(base+"/CPU_ROUND");f<<round;}std::string out=base+"/case"+std::to_string(round);std::vector<Job>jobs;
for(int i=0;i<3;i++){Job j;j.label=i==0?"K":i==1?"V":"Ocarry";j.N=i==2?2048:128;j.K=i==2?128:2048;j.mode=i==2;j.xb.resize(j.K);j.wb.resize(j.N*j.K);j.x.resize(j.K);j.w.resize(j.N*j.K);j.out.resize(j.N);j.bits.resize(j.N);j.xs.resize(j.K);j.xe.resize(j.K);j.xg.resize(j.K);j.ws.resize(j.N*j.K);j.we.resize(j.N*j.K);j.wg.resize(j.N*j.K);j.gold=load<uint16_t>(R+"/"+j.label+"_GPU.bin");j.expected=load<float>(R+"/"+j.label+"_F32_reference.bin");if(j.mode){j.carry.resize(j.N);j.bias.resize(j.N);}jobs.push_back(std::move(j));}
SimRoiStart();
for(int i=0;i<3;i++){auto&j=jobs[i];uint64_t h[8];rx(h,64);if(h[0]!=(j.mode?2:1)||h[1]!=(unsigned)i||h[2]!=(unsigned)j.N||h[3]!=(unsigned)j.K||h[4]!=j.K*2ULL||h[5]!=j.K*j.N*2ULL||h[6]!=(j.mode?j.N*4ULL:0)||h[7]!=(j.mode?j.N*2ULL:0))throw std::runtime_error("CPU descriptor");rx(j.xb.data(),h[4]);rx(j.wb.data(),h[5]);if(j.mode){rx(j.carry.data(),h[6]);rx(j.bias.data(),h[7]);}
marker(100+i*10);for(int k=0;k<j.K;k++)j.x[k]=dec(j.xb[k]);for(int k=0;k<j.K*j.N;k++)j.w[k]=dec(j.wb[k]);if(j.mode)for(int n=0;n<j.N;n++)j.out[n]=j.carry[n];marker(101+i*10);
if(!j.mode){extract_parts(j.x.data(),j.K,j.xs.data(),j.xe.data(),j.xg.data());extract_parts(j.w.data(),j.K*j.N,j.ws.data(),j.we.data(),j.wg.data());tc_matmul_opt(j.xs.data(),j.xe.data(),j.xg.data(),j.ws.data(),j.we.data(),j.wg.data(),j.out.data(),1,j.K,j.N);}else{for(int k=0;k<j.K;k+=16)tc_block_fma_batch(j.out.data(),j.x.data()+k,j.w.data()+k*j.N,1,16,j.N);}
marker(102+i*10);for(int n=0;n<j.N;n++){float a=j.mode?j.out[n]+dec(j.bias[n]):j.out[n];j.bits[n]=enc(a);}marker(103+i*10);tx(h,64);tx(j.out.data(),j.N*4);tx(j.bits.data(),j.N*2);
}
SimRoiEnd();
for(auto&j:jobs){save(out+"/CPU_"+j.label+"_F32.bin",j.out);save(out+"/CPU_"+j.label+"_BF16.bin",j.bits);if(std::memcmp(j.out.data(),j.expected.data(),j.N*4)||std::memcmp(j.bits.data(),j.gold.data(),j.N*2))throw std::runtime_error("CPU bits "+j.label);}
std::ofstream(out+"/CPU_PASS.json")<<"{\"state\":\"PASS_ACTUAL_CPU_SERVICE\",\"FP32_elements\":2304,\"BF16_GPU_elements\":2304,\"cache_coherence_timing_certified\":false}";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}

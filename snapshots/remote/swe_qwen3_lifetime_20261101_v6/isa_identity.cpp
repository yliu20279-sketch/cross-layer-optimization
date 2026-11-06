#include <fstream>
#include <vector>
#include <algorithm>
#include <stdexcept>
#include <cstdint>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#include "sim_api.h"
#include "cache_evict.h"
#include "cpu_services.h"
static unsigned long drain(){unsigned long cmd=5,a=0x534d4344UL,b=0x445241494eUL;asm volatile("xchg %%bx,%%bx" : "+a"(cmd),"+b"(a),"+c"(b) : : "memory");return cmd;}
int main(int argc,char**argv){if(argc!=3)return 2;std::string root=argv[1];
 int fd=open((root+"/EXP16_ALL_FP32.bin").c_str(),O_RDONLY);exp_table=(const float*)mmap(nullptr,1ULL<<34,PROT_READ,MAP_PRIVATE,fd,0);close(fd);
 fd=open((root+"/SILU_ALL_BF16.bin").c_str(),O_RDONLY);silu_table=(const std::uint16_t*)mmap(nullptr,131072,PROT_READ,MAP_PRIVATE,fd,0);close(fd);
 if(exp_table==MAP_FAILED||silu_table==MAP_FAILED)return 3;
 LruSoftwareMaintenance cache;std::ofstream trace(root+"/ISA_POSITIVE_TARGET_IO.txt");
 SimRoiStart();
 auto call=[&](std::uint64_t kind,std::vector<char>in,std::size_t bytes,std::uint64_t a=0,std::uint64_t b=0,std::uint64_t c=0){std::uint64_t h[8]={5,kind,in.size(),bytes,a,b,c};std::vector<char>out(bytes);service(h,in,out);trace<<kind<<":"<<out.size()<<"\n";return out;};
 std::vector<char>zero(512);auto soft=call(5,zero,512,1,128,0);if(((float*)soft.data())[0]!=1.0f/128)return 4;
 std::vector<char>ones(256);for(int i=0;i<128;i++)((std::uint16_t*)ones.data())[i]=0x3f80;
 auto norm=call(3,ones,268,1,128,0x358637bd);if(((std::uint16_t*)norm.data())[0]!=0x3f80)return 5;
 for(int i=0;i<128;i++)((float*)zero.data())[i]=float(i);auto top=call(6,zero,96,1);if(((std::int64_t*)(top.data()+32))[0]!=127)return 6;
 auto a=call(24,{},32,64,0,1);auto version=((std::uint64_t*)a.data())[1];call(25,{},32,0,version,0);auto freed=call(26,{},48,1);if(((std::uint64_t*)freed.data())[0]!=1)return 7;
 bool refused=false;try{call(25,{},32,0,version,0);}catch(const std::exception&){refused=true;}if(!refused)return 8;
 ((std::uint64_t*)zero.data())[0]=37;cache.maintain(zero.data(),zero.size());if(drain()!=0x534d4344UL)return 9;
 trace.flush();SimRoiEnd();std::ofstream(argv[2])<<"PASS_REPRESENTATIVE_CPU_SOFTWARE_AND_LIFETIME_ISA\n"<<"ADDR "<<(std::uintptr_t)exp_table<<" "<<(std::uintptr_t)silu_table<<" "<<(std::uintptr_t)zero.data()<<" "<<(std::uintptr_t)ones.data()<<" "<<(std::uintptr_t)soft.data()<<"\n";return 0;}

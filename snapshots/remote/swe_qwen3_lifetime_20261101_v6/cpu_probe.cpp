
#include <fstream>
#include <vector>
#include <algorithm>
#include <stdexcept>
#include <cstdint>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#include "cpu_services.h"
extern "C" int init(const char*root){std::string r=root;int f=open((r+"/EXP16_ALL_FP32.bin").c_str(),O_RDONLY);exp_table=(const float*)mmap(nullptr,1ULL<<34,PROT_READ,MAP_PRIVATE,f,0);close(f);f=open((r+"/SILU_ALL_BF16.bin").c_str(),O_RDONLY);silu_table=(const std::uint16_t*)mmap(nullptr,131072,PROT_READ,MAP_PRIVATE,f,0);close(f);return exp_table==MAP_FAILED||silu_table==MAP_FAILED;}
extern "C" int serve(unsigned long long kind,const void*x,unsigned long long ib,void*y,unsigned long long ob,unsigned long long a,unsigned long long b,unsigned long long c){try{std::uint64_t h[8]={5,kind,ib,ob,a,b,c};std::vector<char>in((const char*)x,(const char*)x+ib),out(ob);service(h,in,out);memcpy(y,out.data(),ob);return 0;}catch(...){return -1;}}

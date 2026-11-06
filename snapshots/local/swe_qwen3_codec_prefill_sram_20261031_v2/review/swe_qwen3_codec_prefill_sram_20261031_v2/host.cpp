#include <fstream>
#include <vector>
#include <map>
#include <string>
#include <cstdint>
#include <stdexcept>
#include <iostream>
#include <cstdlib>
#include <cstring>
#include <algorithm>
#include <immintrin.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include "apis_c.h"
#include "sim_api.h"
#include "npusim_tensor_codec.h"
using U=std::uint64_t;
std::vector<char> load(std::string p){std::ifstream f(p,std::ios::binary|std::ios::ate);auto n=f.tellg();if(n<=0)throw std::runtime_error("input");std::vector<char>a(n);f.seekg(0);f.read(a.data(),n);if(!f)throw std::runtime_error("short input");return a;}
void flush(void*p,size_t n){auto b=(std::uintptr_t)p&~std::uintptr_t(63);for(;b<(std::uintptr_t)p+n;b+=64)_mm_clflush((void*)b);_mm_sfence();}
int main(int argc,char**argv){try{
 std::string root=argv[1],out=root+"/../case"+std::getenv("SWE_RUN_ROUND");std::ifstream shards(root+"/shards.txt");std::map<std::string,std::pair<char*,U>> maps;std::string path;U n,total=0;
 while(shards>>path>>n){int fd=open(path.c_str(),O_RDONLY);struct stat st;if(fd<0||fstat(fd,&st)||n!=(U)st.st_size)throw std::runtime_error("shard size");void*p=mmap(nullptr,n,PROT_READ,MAP_PRIVATE,fd,0);close(fd);if(p==MAP_FAILED)throw std::runtime_error("mmap");maps[path]={(char*)p,n};total+=n;}
 if(maps.size()!=16||total+16*1024*1024>128ULL*1024*1024*1024)throw std::runtime_error("host bound");
 std::ifstream plan(root+"/plan.txt");U rank,e,token,offset,bytes;std::string shard,xp,gp;
 if(!(plan>>rank>>e>>token>>shard>>offset>>bytes>>xp>>gp)||rank!=0||bytes!=3145728||offset+bytes>maps.at(shard).second)throw std::runtime_error("case");
 auto x=load(xp),gold=load(gp);if(x.size()!=24576||gold.size()!=9216)throw std::runtime_error("shape");
 std::vector<float> xf(12288),wf(bytes/2),y(4608);std::vector<std::uint16_t> bits(4608);
 SimRoiStart();
 auto w=maps.at(shard).first+offset;
 for(U i=0;i<12288;i++){std::uint16_t b;std::memcpy(&b,x.data()+2*i,2);xf[i]=NPUSim::bf16BitsToFloat(b);}
 for(U i=0;i<bytes/2;i++){std::uint16_t b;std::memcpy(&b,w+2*i,2);wf[i]=NPUSim::bf16BitsToFloat(b);}
 flush(x.data(),x.size());flush(xf.data(),xf.size()*4);flush(w,bytes);flush(wf.data(),wf.size()*4);
 U h[]={rank,e,token,2048,768,bytes,24576,0x00040003};
 auto send=[&](void*p,U n){for(U off=0;off<n;off+=65536)if(InterChiplet::sendMessage(0,4,0,12,(char*)p+off,std::min<U>(65536,n-off))<0)throw std::runtime_error("send");};
 send(h,64);send(x.data(),24576);send(xf.data(),49152);send(w,bytes);send(wf.data(),bytes*2);
 flush(y.data(),y.size()*4);
 if(InterChiplet::receiveMessage(0,12,0,4,y.data(),y.size()*4)<0)throw std::runtime_error("receive");flush(y.data(),y.size()*4);
 for(U i=0;i<4608;i++)bits[i]=NPUSim::floatToBf16Bits(y[i]);
 if(std::memcmp(bits.data(),gold.data(),9216))throw std::runtime_error("strict BF16 output mismatch");
 SimRoiEnd();
 std::ofstream(out+"/CPU_RAW_FP32.bin",std::ios::binary).write((char*)y.data(),18432);
 std::ofstream(out+"/CPU_BF16.bin",std::ios::binary).write((char*)bits.data(),9216);
 std::ofstream(out+"/CPU_EXPANDED_X.bin",std::ios::binary).write((char*)xf.data(),49152);
 std::ofstream(out+"/CPU_EXPANDED_W.bin",std::ios::binary).write((char*)wf.data(),bytes*2);
 std::ofstream(out+"/CPU_PASS.json")<<"{\"state\":\"PASS_ACTUAL_CPU_CODEC_BF16_GATE\",\"host_mapped_bytes\":"<<total<<",\"decoded_elements\":"<<(12288+bytes/2)<<",\"encoded_elements\":4608,\"cache_flush_requested\":true,\"cache_maintenance_timing_certified\":false}";
 return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}

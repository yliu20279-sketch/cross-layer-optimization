#include <fstream>
#include <vector>
#include <map>
#include <string>
#include <cstdint>
#include <stdexcept>
#include <iostream>
#include <cstdlib>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include "apis_c.h"
#include "sim_api.h"
std::vector<char> load(std::string path){std::ifstream f(path,std::ios::binary|std::ios::ate);auto n=f.tellg();if(n<=0)throw std::runtime_error("input");std::vector<char>a(n);f.seekg(0);f.read(a.data(),n);if(!f)throw std::runtime_error("short input");return a;}
struct Case {std::uint64_t rank,e,token,offset,bytes;std::string shard;std::vector<char>x,gold;};
int main(int argc,char**argv){try{
 std::string root=argv[1],out=root+"/../case"+std::getenv("SWE_RUN_ROUND");std::ifstream shards(root+"/shards.txt");std::map<std::string,std::pair<char*,std::uint64_t>> maps;std::string path;std::uint64_t n,total=0;
 while(shards>>path>>n){int fd=open(path.c_str(),O_RDONLY);struct stat st;if(fd<0||fstat(fd,&st)||n!=(std::uint64_t)st.st_size)throw std::runtime_error("shard size");void*p=mmap(nullptr,n,PROT_READ,MAP_PRIVATE,fd,0);close(fd);if(p==MAP_FAILED)throw std::runtime_error("host backing mmap");maps[path]={(char*)p,n};total+=n;}
 if(maps.size()!=16||total+131072+1048576>128ULL*1024*1024*1024)throw std::runtime_error("128GiB host backing bound");
 std::ifstream plan(root+"/plan.txt");std::vector<Case> cases;Case c;std::string xp,gp;
 while(plan>>c.rank>>c.e>>c.token>>c.shard>>c.offset>>c.bytes>>xp>>gp){c.x=load(xp);c.gold=load(gp);if(c.rank!=cases.size()||c.x.size()!=4096||c.gold.size()!=1536||c.offset+c.bytes>maps.at(c.shard).second)throw std::runtime_error("case contract");cases.push_back(c);}
 if(cases.size()!=16)throw std::runtime_error("16 cases required");
 SimRoiStart();
 for(auto& v:cases){
  std::uint64_t h[]={v.rank,v.e,v.token,2048,768,v.bytes,4096,3};
  if(InterChiplet::sendMessage(0,4,0,12,h,sizeof(h))<0)return 3;
  if(InterChiplet::sendMessage(0,4,0,12,v.x.data(),v.x.size())<0)return 3;
  for(std::uint64_t off=0;off<v.bytes;off+=65536){auto size=std::min<std::uint64_t>(65536,v.bytes-off);if(InterChiplet::sendMessage(0,4,0,12,maps.at(v.shard).first+v.offset+off,size)<0)return 3;}
  std::vector<char> y(v.gold.size());if(InterChiplet::receiveMessage(0,12,0,4,y.data(),y.size())<0)return 4;
  if(y!=v.gold)throw std::runtime_error("BF16 gate projection mismatch on N"+std::to_string(v.rank));
  std::ofstream(out+"/N"+std::to_string(v.rank)+"_CPU_ACTUAL.bin",std::ios::binary).write(y.data(),y.size());
 }
 SimRoiEnd();std::ofstream(out+"/CPU_PASS.json")<<"{\"state\":\"PASS_16_REAL_BF16_GATE_PROJECTIONS\",\"host_mapped_model_bytes\":"<<total<<"}";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}

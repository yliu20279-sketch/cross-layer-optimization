#include <fstream>
#include <vector>
#include <map>
#include <string>
#include <cstdint>
#include <stdexcept>
#include <iostream>
#include <cstdlib>
#include <algorithm>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include "apis_c.h"
#include "sim_api.h"
std::vector<char> load(std::string p){std::ifstream f(p,std::ios::ate|std::ios::binary);auto n=f.tellg();if(n<=0)throw std::runtime_error("input");std::vector<char>a(n);f.seekg(0);f.read(a.data(),n);if(!f)throw std::runtime_error("short input");return a;}
void send(const void*p,size_t n){for(size_t off=0;off<n;off+=65536)if(InterChiplet::sendMessage(0,4,0,12,(char*)p+off,std::min<size_t>(65536,n-off))<0)throw std::runtime_error("send");}
void receive(void*p,size_t n){for(size_t off=0;off<n;off+=65536)if(InterChiplet::receiveMessage(0,12,0,4,(char*)p+off,std::min<size_t>(65536,n-off))<0)throw std::runtime_error("receive");}
struct Param {std::uint64_t id,offset,bytes,N,K,owner;std::string shard;};
int main(int argc,char**argv){try{
 std::string root=argv[1],out=root+"/../case"+std::getenv("SWE_RUN_ROUND");std::map<std::string,std::pair<char*,std::uint64_t>> maps;std::ifstream shards(root+"/shards.txt");std::string path;std::uint64_t n,total=0;
 while(shards>>path>>n){int fd=open(path.c_str(),O_RDONLY);struct stat st;if(fd<0||fstat(fd,&st)||n!=(std::uint64_t)st.st_size)throw std::runtime_error("shard");void*p=mmap(nullptr,n,PROT_READ,MAP_PRIVATE,fd,0);close(fd);if(p==MAP_FAILED)throw std::runtime_error("mmap");maps[path]={(char*)p,n};total+=n;}
 if(maps.size()!=16||total+512*1024*1024>128ULL*1024*1024*1024)throw std::runtime_error("host capacity");
 std::ifstream params(root+"/parameters.txt");std::vector<Param> ps;Param p;
 while(params>>p.id>>p.shard>>p.offset>>p.bytes>>p.N>>p.K>>p.owner){if(p.id!=ps.size()||p.offset+p.bytes>maps.at(p.shard).second)throw std::runtime_error("parameter table");ps.push_back(p);}
 if(ps.size()!=786)throw std::runtime_error("786 original parameters");
 std::vector<std::vector<char>> inputs,golds;for(auto phase:{"prefill","decode"}){inputs.push_back(load(root+"/"+phase+"_input.bin"));golds.push_back(load(root+"/"+phase+"_gold.bin"));}
 std::uint64_t jobs=0,fetches=0;SimRoiStart();
 for(int phase=0;phase<2;phase++){
  std::uint64_t inputh[8]={4,(unsigned)phase,inputs[phase].size()};send(inputh,64);send(inputs[phase].data(),inputs[phase].size());
  while(true){
   std::uint64_t h[8];receive(h,64);
   if(h[0]==3){if(h[1]!=(unsigned)phase||h[2]!=golds[phase].size())throw std::runtime_error("result descriptor");std::vector<char>y(h[2]);receive(y.data(),y.size());if(y!=golds[phase])throw std::runtime_error("full layer BF16 mismatch");std::ofstream(out+"/"+(phase==0?"prefill":"decode")+"_CPU_ACTUAL.bin",std::ios::binary).write(y.data(),y.size());break;}
   auto id=h[1]&0xffffffffULL;if(id>=ps.size())throw std::runtime_error("parameter id");auto&v=ps[id];char*w=maps.at(v.shard).first+v.offset;
   if(h[0]==1){if(h[2]!=v.bytes)throw std::runtime_error("parameter bytes");send(w,v.bytes);fetches++;}
   else if(h[0]==2){
    auto M=h[2],N=h[3],K=h[4];if(N!=v.N||K!=v.K||h[5]!=2*M*K||h[6]!=v.bytes||h[7]!=v.owner||!v.owner||M<1||M>19)throw std::runtime_error("matrix shape/owner");
    std::vector<char>x(h[5]),y(4*M*N);receive(x.data(),x.size());send(x.data(),x.size());send(w,v.bytes);receive(y.data(),y.size());send(y.data(),y.size());jobs++;
   }else throw std::runtime_error("command");
  }
 }
 SimRoiEnd();std::ofstream(out+"/CPU_PASS.json")<<"{\"state\":\"PASS_FULL_TWO_LAYER_PREFILL_DECODE\",\"model_mapped_bytes\":"<<total<<",\"remote_jobs\":"<<jobs<<",\"parameter_fetches\":"<<fetches<<"}";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}

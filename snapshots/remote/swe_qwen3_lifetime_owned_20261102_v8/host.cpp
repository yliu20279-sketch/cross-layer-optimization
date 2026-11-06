#include <fstream>
#include <cerrno>
#include <immintrin.h>
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
#include "cache_evict.h"
static LruSoftwareMaintenance* software_cache=nullptr;
static std::ofstream* cache_log=nullptr;static std::uint64_t cache_sequence=0;
static unsigned long drain_directory(){unsigned long cmd=5,a=0x534d4344UL,b=0x445241494eUL;asm volatile("xchg %%bx,%%bx" : "+a"(cmd),"+b"(a),"+c"(b) : : "memory");return cmd;}
static void maintain(const void*p,size_t n,const char*kind){
 if(!n)return;if(!software_cache||!cache_log)throw std::runtime_error("cache protocol not initialized");
 software_cache->maintain(p,n);if(drain_directory()!=0x534d4344UL)throw std::runtime_error("directory drain hook missing");
 *cache_log<<"{\"sequence\":"<<++cache_sequence<<",\"address\":"<<(std::uintptr_t)p<<",\"bytes\":"<<n<<",\"kind\":\""<<kind<<"\",\"completed\":true}\n";
}
void send(const void*p,size_t n){maintain(p,n,"before_send");for(size_t off=0;off<n;off+=65536)if(InterChiplet::sendMessage(0,4,0,12,(char*)p+off,std::min<size_t>(65536,n-off))<0)throw std::runtime_error("send");}
void receive(void*p,size_t n){maintain(p,n,"before_receive");for(size_t off=0;off<n;off+=65536)if(InterChiplet::receiveMessage(0,12,0,4,(char*)p+off,std::min<size_t>(65536,n-off))<0)throw std::runtime_error("receive");maintain(p,n,"after_receive");}

#include "cpu_services.h"
struct Param {std::uint64_t id,offset,bytes,N,K,owner;std::string shard;};
int main(int argc,char**argv){try{
 std::string root=argv[1],out=root+"/../case"+std::getenv("SWE_RUN_ROUND");std::map<std::string,std::pair<char*,std::uint64_t>> maps;std::ifstream shards(root+"/shards.txt");std::string path;std::uint64_t n,total=0;
 while(shards>>path>>n){int fd=open(path.c_str(),O_RDONLY);struct stat st;if(fd<0||fstat(fd,&st)||n!=(std::uint64_t)st.st_size)throw std::runtime_error("shard");void*p=mmap(nullptr,n,PROT_READ,MAP_PRIVATE,fd,0);close(fd);if(p==MAP_FAILED)throw std::runtime_error("mmap");maps[path]={(char*)p,n};total+=n;}
 if(maps.size()!=16||total+512*1024*1024>128ULL*1024*1024*1024)throw std::runtime_error("host capacity");
 if(::mkdir(out.c_str(),0755)&&errno!=EEXIST)throw std::runtime_error("case directory");
 std::ifstream params(root+"/parameters.txt");std::vector<Param> ps;Param p;
 while(params>>p.id>>p.shard>>p.offset>>p.bytes>>p.N>>p.K>>p.owner){if(p.id!=ps.size()||p.offset+p.bytes>maps.at(p.shard).second)throw std::runtime_error("parameter table");ps.push_back(p);}
 if(ps.size()!=786)throw std::runtime_error("786 original parameters");
 std::vector<std::vector<char>> inputs,golds;for(auto phase:{"prefill","decode"}){inputs.push_back(load(root+"/"+phase+"_input.bin"));golds.push_back(load(root+"/"+phase+"_gold.bin"));}
 auto map_table=[&](const std::string&name,std::uint64_t expected){int fd=open((root+"/../"+name).c_str(),O_RDONLY);struct stat st;if(fd<0||fstat(fd,&st)||(std::uint64_t)st.st_size!=expected)throw std::runtime_error("math table size");void*p=mmap(nullptr,expected,PROT_READ,MAP_PRIVATE,fd,0);close(fd);if(p==MAP_FAILED)throw std::runtime_error("math mmap");return p;};
 for(auto phase:{"prefill","decode"})for(auto name:{"cos","sin"})positional_constants.push_back(load(root+"/"+phase+"_"+name+".bin"));
 exp_table=(const float*)map_table("EXP16_ALL_FP32.bin",1ULL<<34);silu_table=(const std::uint16_t*)map_table("SILU_ALL_BF16.bin",131072);
 if(total+(1ULL<<34)+131072+(512ULL<<20)>128ULL*1024*1024*1024)throw std::runtime_error("host with software data capacity");
 LruSoftwareMaintenance cache;software_cache=&cache;std::ofstream cache_stream(out+"/CPU_CACHE_GATES.jsonl");if(!cache_stream)throw std::runtime_error("cache gate log open");cache_log=&cache_stream;
 std::ofstream service_log(out+"/CPU_SERVICE_COMPLETIONS.jsonl");std::uint64_t software_jobs=0,jobs=0,fetches=0;SimRoiStart();
 for(int phase=0;phase<2;phase++){
  std::uint64_t inputh[8]={4,(unsigned)phase,inputs[phase].size()};send(inputh,64);send(inputs[phase].data(),inputs[phase].size());
  while(true){
   std::uint64_t h[8];receive(h,64);
   if(h[0]==3){if(h[1]!=(unsigned)phase||h[2]!=golds[phase].size())throw std::runtime_error("result descriptor");std::vector<char>y(h[2]);receive(y.data(),y.size());if(y!=golds[phase])throw std::runtime_error("full layer BF16 mismatch");std::ofstream(out+"/"+(phase==0?"prefill":"decode")+"_CPU_ACTUAL.bin",std::ios::binary).write(y.data(),y.size());break;}
   if(h[0]==5){if(h[2]>(128ULL<<20)||h[3]>(128ULL<<20))throw std::runtime_error("software buffer bound");std::vector<char>in(h[2]),outbuf(h[3]);receive(in.data(),in.size());service(h,in,outbuf);send(outbuf.data(),outbuf.size());software_jobs++;service_log<<"{\"kind\":"<<h[1]<<",\"input_bytes\":"<<h[2]<<",\"output_bytes\":"<<h[3]<<"}\n";continue;}
   auto id=h[1]&0xffffffffULL;if(id>=ps.size())throw std::runtime_error("parameter id");auto&v=ps[id];char*w=maps.at(v.shard).first+v.offset;
   if(h[0]==1){if(h[2]!=v.bytes)throw std::runtime_error("parameter bytes");send(w,v.bytes);fetches++;}
   else if(h[0]==2){
    auto M=h[2],N=h[3],K=h[4];if(N!=v.N||K!=v.K||h[5]!=2*M*K||h[6]!=v.bytes||h[7]!=v.owner||!v.owner||M<1||M>19)throw std::runtime_error("matrix shape/owner");
    std::vector<char>x(h[5]),y(4*M*N);receive(x.data(),x.size());std::vector<float>xf(M*K),wf(N*K);
    for(std::uint64_t i=0;i<M*K;i++){std::uint16_t bits;memcpy(&bits,x.data()+2*i,2);xf[i]=dec(bits);}for(std::uint64_t i=0;i<N*K;i++){std::uint16_t bits;memcpy(&bits,w+2*i,2);wf[i]=dec(bits);}
    send(x.data(),x.size());send(xf.data(),xf.size()*4);send(w,v.bytes);send(wf.data(),wf.size()*4);receive(y.data(),y.size());send(y.data(),y.size());jobs++;
   }else throw std::runtime_error("command");
  }
 }
 // The final numeric result does not release KV session ownership.
 while(true){
  std::uint64_t h[8];receive(h,64);
  if(h[0]==6){
   std::uint64_t state[4];lifetime_allocator.inspect(state);
   if(h[1]!=0x51424d4bULL||state[0]||state[1]||state[2]||state[3]!=(208ULL<<20))throw std::runtime_error("teardown with live ownership");
   std::uint64_t ack[8]={6,0x51424d4bULL,0,0,0,208ULL<<20,0,0};send(ack,64);
   std::ofstream(out+"/CPU_TEARDOWN_PASS.json")<<"{\"state\":\"PASS_EMPTY_ARENA_ACK\"}";break;
  }
  if(h[0]!=5||(h[1]!=25&&h[1]!=26&&h[1]!=28&&h[1]!=29)||h[2]||h[3]>(128ULL<<20))throw std::runtime_error("non-cleanup command after final result");
  std::vector<char>in,outbuf(h[3]);service(h,in,outbuf);send(outbuf.data(),outbuf.size());
  service_log<<"{\"kind\":"<<h[1]<<",\"input_bytes\":0,\"output_bytes\":"<<h[3]<<"}\n";
 }
 SimRoiEnd();service_log.flush();cache_stream.flush();std::ofstream(out+"/CPU_PASS.json")<<"{\"state\":\"PASS_FULL_TWO_LAYER_PREFILL_DECODE\",\"model_mapped_bytes\":"<<total<<",\"remote_jobs\":"<<jobs<<",\"parameter_fetches\":"<<fetches<<"}";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}

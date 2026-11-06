#pragma once
#include <cstdint>
#include <cstdlib>
#include <vector>
#include <fstream>
#include <string>
#include <stdexcept>
// Permute complete 256KiB row groups; all bytes/rows remain bijective.
static uint32_t frame_calc(uint32_t p,int stripe,uint32_t begin){
 if(p<begin)return p;
 uint32_t j=p-begin,b,k;
 if(stripe==1){b=j%16;k=j/16;}else{b=(j/4)%16;k=(j/64)*4+j%4;}
 uint32_t field=(b>>2)|((b&3)<<2);
 return begin+(k/4)*64+field*4+k%4;
}
struct FrameMapper{
 std::string mode;int stripe=4;uint32_t begin=0;double delay=0;std::vector<uint32_t> table;uint64_t attempts=0,mapped=0;
 FrameMapper(){
  auto env=[](const char*k,const char*d){auto p=std::getenv(k);return std::string(p?p:d);};
  mode=env("HB_FRAME_MAP_MODE","none");stripe=std::stoi(env("HB_STRIPE_PAGES","4"));begin=std::stoul(env("HB_FRAME_SCOPE_START","0"))/4096;delay=std::stod(env("HB_ADDR_LOOKUP_DELAY_NS","0"));
  if(mode!="none"&&mode!="formula"&&mode!="table")throw std::runtime_error("bad frame map mode");
  if((stripe!=1&&stripe!=4)||begin%64||begin>=131072||delay<0)throw std::runtime_error("bad native frame geometry");
  if(mode=="table"){
   table.resize(131072);std::ifstream in(env("HB_FRAME_MAP_BIN",""),std::ios::binary);in.read(reinterpret_cast<char*>(table.data()),table.size()*4);if(in.gcount()!=long(table.size()*4)||in.peek()!=EOF)throw std::runtime_error("bad frame table size");
   std::vector<bool>seen(131072,false);for(uint32_t p=0;p<131072;p++){uint32_t q=table[p];if(q>=131072||seen[q]||(p<begin&&q!=p))throw std::runtime_error("frame table not valid bijection");seen[q]=true;}
  }
 }
 static FrameMapper& get(){static FrameMapper m;return m;}
 uint64_t apply(uint64_t address){
  attempts++;if(mode=="none")return address;if(address>=536870912ULL)throw std::runtime_error("frame address outside512MiB");uint32_t p=uint32_t(address>>12);if(p<begin)return address;mapped++;uint32_t q=mode=="table"?table[p]:frame_calc(p,stripe,begin);return (uint64_t(q)<<12)|(address&4095ULL);
 }
 double issue_delay(uint64_t physical){return mode!="none"&&(physical>>12)>=begin?delay:0;}
 static void report(const std::string&out){auto&m=get();std::ofstream f(out+"/frame_mapping_runtime.json");f<<"{\"mode\":\""<<m.mode<<"\",\"stripe_pages\":"<<m.stripe<<",\"scope_start_bytes\":"<<uint64_t(m.begin)*4096<<",\"lookup_delay_ns\":"<<m.delay<<",\"attempts\":"<<m.attempts<<",\"mapped_attempts\":"<<m.mapped<<",\"table_bytes\":"<<m.table.size()*4<<"}\n";}
};

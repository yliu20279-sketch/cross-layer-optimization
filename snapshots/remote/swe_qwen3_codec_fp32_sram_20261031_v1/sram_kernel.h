#pragma once
#include <array>
#include <vector>
#include <cstring>
#include <fstream>
#include <algorithm>
#include <stdexcept>
#include <cstdint>
class ExplicitSramKernel {
 NPUSim::ChipletNpuRuntime& rt;
 std::vector<unsigned char> mem;
 std::array<std::uint64_t,8> free_bank{},read_beats{},write_beats{};
 std::uint64_t bank_cycles=0,compute_cycles=0,mul_ops=0,add_ops=0,reduce_ops=0,events=0;
 std::ofstream rows;
 static constexpr std::uint64_t X=0,W=8192,A=1048576,Y=2097152;
 void check(std::uint64_t a,std::uint64_t n){if(!n||a+n>mem.size())throw std::runtime_error("SRAM bounds");}
 void access(const std::vector<std::pair<std::uint64_t,std::uint64_t>>& req,bool write){
  auto issue=rt.chipCycle(),done=issue;
  for(auto p:req){check(p.first,p.second);for(auto line=p.first/32;line<=(p.first+p.second-1)/32;line++){
   unsigned b=line%8;auto start=std::max<std::uint64_t>(issue,free_bank[b]);free_bank[b]=start+1;done=std::max<std::uint64_t>(done,start+1);(write?write_beats[b]:read_beats[b])++;
  }}
  bank_cycles+=done-issue;rt.chipCycle()=done;
 }
 void op(std::uint64_t count,bool reduce,std::uint64_t code){
  NPUSim::NpuEventRecorder r;if(reduce)r.reduceCompute(code,count);else r.vectorCompute(code,count);
  auto before=rt.chipCycle();auto result=rt.scheduleProgram(r.events());compute_cycles+=rt.chipCycle()-before;events+=result.entries.size();
 }
 float get(std::uint64_t a){float f;std::memcpy(&f,mem.data()+a,4);return f;}
 void put(std::uint64_t a,float f){std::memcpy(mem.data()+a,&f,4);}
public:
 explicit ExplicitSramKernel(NPUSim::ChipletNpuRuntime&r,const std::string&dir):rt(r),mem(4194304),rows(dir+"/SRAM_ROWS.csv"){
  rows<<"row,start,done,weight_version,weight_last_reader\n";
 }
 void run(std::uint64_t xhb,std::uint64_t whb,std::uint64_t yhb,int K,int N,const std::string&dir){
  if(K!=2048||N!=768)throw std::runtime_error("unsupported geometry, no silent fallback");
  const auto begin=rt.chipCycle();rt.load(xhb,mem.data()+X,K*4,"FP32_X_to_SRAM");access({{X,K*4ULL}},true);
  std::uint64_t version=0,last_reader=0;
  for(int n0=0;n0<N;n0+=64){
   if(rt.chipCycle()<last_reader)throw std::runtime_error("weight overwrite before last reader");version++;
   rt.load(whb+n0*K*4ULL,mem.data()+W,64*K*4ULL,"FP32_W_tile_to_SRAM");access({{W,64*K*4ULL}},true);
   for(int nn=0;nn<64;nn++){
    auto row_start=rt.chipCycle();access({{A,256}},true);std::memset(mem.data()+A,0,256);
    for(int k=0;k<K;k+=16){
     auto xa=X+k*4ULL,wa=W+(nn*K+k)*4ULL,aa=A+(k%64)*4ULL;
     access({{xa,64},{wa,64},{aa,64}},false);last_reader=rt.chipCycle();
     float p[16],s[16];for(int j=0;j<16;j++){p[j]=get(xa+j*4)*get(wa+j*4);s[j]=get(aa+j*4);}
     op(16,false,1);mul_ops+=16;for(int j=0;j<16;j++)s[j]=s[j]+p[j];op(16,false,2);add_ops+=16;
     access({{aa,64}},true);for(int j=0;j<16;j++)put(aa+j*4,s[j]);
    }
    for(int half=32;half;half/=2)for(int off=0;off<half;off+=16){
     int n=std::min(16,half-off);auto l=A+off*4ULL,r=A+(off+half)*4ULL;access({{l,n*4ULL},{r,n*4ULL}},false);
     float sums[16];for(int j=0;j<n;j++)sums[j]=get(l+j*4)+get(r+j*4);op(n,true,3);reduce_ops+=n;
     access({{l,n*4ULL}},true);for(int j=0;j<n;j++)put(l+j*4,sums[j]);
    }
    // Aligned K makes the source's tail accumulator identically +0.
    // Its seven constant additions are folded; final +0 remains explicit.
    access({{A,4}},false);float out=get(A)+0.0f;op(1,false,2);add_ops++;
    access({{Y+(n0+nn)*4ULL,4}},true);put(Y+(n0+nn)*4ULL,out);
    rows<<(n0+nn)<<','<<row_start<<','<<rt.chipCycle()<<','<<version<<','<<last_reader<<'\n';
   }
  }
  access({{Y,N*4ULL}},false);rt.store(yhb,mem.data()+Y,N*4ULL,"FP32_result_from_SRAM");rows.flush();
  std::ofstream out(dir+"/LOWERING.json");out<<"{\"state\":\"EXECUTED_FP32_PRIMITIVES_AND_REAL_SRAM\",\"mul_ops\":"<<mul_ops<<",\"add_ops\":"<<add_ops<<",\"reduce_ops\":"<<reduce_ops<<",\"native_compute_events\":"<<events<<",\"compute_cycles\":"<<compute_cycles<<",\"bank_service_cycles\":"<<bank_cycles<<",\"begin\":"<<begin<<",\"complete\":"<<rt.chipCycle()<<",\"weight_versions\":"<<version<<",\"bank_mapping\":\"striped32_single_shared_port_research_overlay\",\"read_beats\":[";
  for(int b=0;b<8;b++)out<<(b?",":"")<<read_beats[b];out<<"],\"write_beats\":[";for(int b=0;b<8;b++)out<<(b?",":"")<<write_beats[b];out<<"]}";
 }
};

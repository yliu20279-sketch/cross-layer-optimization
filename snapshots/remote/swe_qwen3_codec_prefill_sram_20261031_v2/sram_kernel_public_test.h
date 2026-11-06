#pragma once
#include <array>
#include <vector>
#include <cstring>
#include <fstream>
#include <algorithm>
#include <stdexcept>
#include <cstdint>
class ExplicitSramKernel {public:
 NPUSim::ChipletNpuRuntime& rt;
 std::vector<unsigned char> mem;
 std::array<std::uint64_t,8> free_bank{},read_beats{},write_beats{};
 std::uint64_t bank_cycles=0,compute_cycles=0,mul_ops=0,add_ops=0,reduce_ops=0,events=0;
 std::ofstream rows;
 static constexpr std::uint64_t X=0,W=65536,A=1048576,Y=2097152;
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
  const auto begin=rt.chipCycle();rt.load(xhb,mem.data()+X,6*K*4,"FP32_X_to_SRAM");access({{X,6*K*4ULL}},true);
  std::uint64_t version=0,last_reader=0;
  for(int n0=0;n0<N;n0+=64){
   if(rt.chipCycle()<last_reader)throw std::runtime_error("weight overwrite before last reader");version++;
   rt.load(whb+n0*K*4ULL,mem.data()+W,64*K*4ULL,"FP32_W_tile_to_SRAM");access({{W,64*K*4ULL}},true);
   for(int m=0;m<6;m++)for(int sub=0;sub<64;sub+=16){
    auto row_start=rt.chipCycle();const std::uint64_t T=A+128;
    bool first=true;
    for(int k0=0;k0<K;k0+=768){
     access({{A,64}},true);std::memset(mem.data()+A,0,64);
     int end=std::min(K,k0+768);
     for(int kk=k0;kk<end;kk+=2)for(int parity=1;parity>=0;parity--){
      int k=kk+parity;if(k>=end)continue;
      std::vector<std::pair<std::uint64_t,std::uint64_t>> req{{X+(m*K+k)*4ULL,4},{A,64}};
      for(int lane=0;lane<16;lane++)req.push_back({W+((sub+lane)*K+k)*4ULL,4});
      access(req,false);last_reader=rt.chipCycle();float p[16],a[16];
      for(int lane=0;lane<16;lane++){p[lane]=get(X+(m*K+k)*4ULL)*get(W+((sub+lane)*K+k)*4ULL);a[lane]=get(A+lane*4);}
      op(16,false,1);mul_ops+=16;for(int lane=0;lane<16;lane++)a[lane]=a[lane]+p[lane];op(16,false,2);add_ops+=16;
      access({{A,64}},true);for(int lane=0;lane<16;lane++)put(A+lane*4,a[lane]);
     }
     access({{A,64}},false);float acc[16];for(int lane=0;lane<16;lane++)acc[lane]=get(A+lane*4);
     if(!first){access({{T,64}},false);for(int lane=0;lane<16;lane++)acc[lane]=get(T+lane*4)+acc[lane];op(16,false,2);add_ops+=16;}
     access({{T,64}},true);for(int lane=0;lane<16;lane++)put(T+lane*4,acc[lane]);first=false;
    }
    access({{T,64}},false);float result[16];for(int lane=0;lane<16;lane++)result[lane]=get(T+lane*4);
    access({{Y+(m*N+n0+sub)*4ULL,64}},true);for(int lane=0;lane<16;lane++)put(Y+(m*N+n0+sub+lane)*4ULL,result[lane]);
    rows<<(m*N+n0+sub)<<','<<row_start<<','<<rt.chipCycle()<<','<<version<<','<<last_reader<<'\n';
   }
  }
  access({{Y,6*N*4ULL}},false);rt.store(yhb,mem.data()+Y,6*N*4ULL,"FP32_result_from_SRAM");rows.flush();
  std::ofstream out(dir+"/LOWERING.json");out<<"{\"state\":\"EXECUTED_FP32_PRIMITIVES_AND_REAL_SRAM\",\"mul_ops\":"<<mul_ops<<",\"add_ops\":"<<add_ops<<",\"reduce_ops\":"<<reduce_ops<<",\"native_compute_events\":"<<events<<",\"compute_cycles\":"<<compute_cycles<<",\"bank_service_cycles\":"<<bank_cycles<<",\"begin\":"<<begin<<",\"complete\":"<<rt.chipCycle()<<",\"weight_versions\":"<<version<<",\"bank_mapping\":\"striped32_single_shared_port_research_overlay\",\"read_beats\":[";
  for(int b=0;b<8;b++)out<<(b?",":"")<<read_beats[b];out<<"],\"write_beats\":[";for(int b=0;b<8;b++)out<<(b?",":"")<<write_beats[b];out<<"]}";
 }
};

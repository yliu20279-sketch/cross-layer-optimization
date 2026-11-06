#include <memory>
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <vector>
#include <cstring>
#include "npusim_chiplet_runtime.h"
#include "sync_protocol.h"
static std::unique_ptr<NPUSim::ChipletNpuRuntime> rt;
static std::string error;
static int output_fd=-1,input_fd=-1;
static int rank=std::atoi(std::getenv("SWE_RANK"));
static std::ofstream logf;
static std::string bank_report;
extern "C" __attribute__((visibility("default"))) const char* um_error(){return error.c_str();}
#define TRY try{
#define END }catch(const std::exception&e){error=e.what();return -1;}
extern "C" __attribute__((visibility("default"))) int um_init(const char*report){TRY NPUSim::NPUConfig c;c.external_memory_enable=true;c.external_memory_model="chiplet";c.dram_transaction_bytes=32;c.dram_size_bytes=536870912;c.dram_chiplet_x=rank%4;c.dram_chiplet_y=8+rank/4;c.dram_chiplet_burst_bytes=65536;c.dram_chiplet_region_bytes=536870912;c.dram_chiplet_grid_cols=4;c.intra_delay_enable=false;c.mac_unit_count=4096;c.sram_per_mac_bytes=1024;c.vector_ops_per_cycle=16;c.reduce_ops_per_cycle=16;c.sram_bandwidth_bytes_per_cycle=256;c.activation_dtype=c.weight_dtype=c.output_dtype=NPUSim::TensorDType::kBf16;c.accumulator_dtype=NPUSim::TensorDType::kFp32;NPUSim::ChipletNpuRuntimeOptions o;o.self_x=rank%4;o.self_y=rank/4;o.report_directory=report;rt=std::make_unique<NPUSim::ChipletNpuRuntime>(c,o);bank_report=report;logf.open(std::string(report)+"/program.csv");logf<<"label,kind,ops,start,complete\n";return 0;END}
extern "C" __attribute__((visibility("default"))) int um_store(unsigned long long addr,const void*p,unsigned long long n){TRY rt->store(addr,p,n,"actual_tensor_store");return 0;END}
extern "C" __attribute__((visibility("default"))) int um_load(unsigned long long addr,void*p,unsigned long long n){TRY rt->load(addr,p,n,"actual_tensor_load");return 0;END}
extern "C" __attribute__((visibility("default"))) int um_compute(unsigned long long ops,int reduce,const char*label){TRY NPUSim::NpuEventRecorder rec;if(reduce)rec.reduceCompute(1,ops);else rec.vectorCompute(1,ops);auto s=rt->scheduleProgram(rec.events());for(auto&e:s.entries)logf<<label<<","<<reduce<<","<<ops<<","<<e.start_cycle<<","<<e.complete_cycle<<"\n";return 0;END}
extern "C" __attribute__((visibility("default"))) unsigned long long um_now(){return rt->chipCycle();}
static void io(int fd,char*p,size_t n,bool wr){if(fd<0)throw std::runtime_error("FIFO open");while(n){auto k=wr?write(fd,p,n):read(fd,p,n);if(k<=0)throw std::runtime_error("FIFO short");p+=k;n-=k;}}

static void sendbytes(const void*p,unsigned long long n){for(unsigned long long off=0;off<n;off+=65536){auto k=std::min<unsigned long long>(65536,n-off);auto s=InterChiplet::sendSync(rank%4,rank/4,0,4);if(output_fd<0)output_fd=open(s.c_str(),O_WRONLY);io(output_fd,(char*)p+off,k,true);auto t=InterChiplet::writeSync(rt->chipCycle(),rank%4,rank/4,0,4,k,0);rt->chipCycle()=std::max(rt->chipCycle(),(unsigned long long)t);}}
static void recvbytes(void*p,unsigned long long n){for(unsigned long long off=0;off<n;off+=65536){auto k=std::min<unsigned long long>(65536,n-off);auto s=InterChiplet::receiveSync(0,4,rank%4,rank/4);if(input_fd<0)input_fd=open(s.c_str(),O_RDONLY);io(input_fd,(char*)p+off,k,false);auto t=InterChiplet::readSync(rt->chipCycle(),0,4,rank%4,rank/4,k,0);rt->chipCycle()=std::max(rt->chipCycle(),(unsigned long long)t);}}
extern "C" __attribute__((visibility("default"))) int um_net_recv(void*p,unsigned long long n){TRY recvbytes(p,n);return 0;END}
extern "C" __attribute__((visibility("default"))) int um_net_send(const void*p,unsigned long long n){TRY sendbytes(p,n);return 0;END}
extern "C" __attribute__((visibility("default"))) int um_recv(void*p,unsigned long long n){TRY recvbytes(p,n);return 0;END}
extern "C" __attribute__((visibility("default"))) int um_send(const void*p,unsigned long long n){TRY static std::uint64_t phase=0;std::uint64_t h[8]={3,phase++,n};sendbytes(h,64);sendbytes(p,n);return 0;END}
extern "C" __attribute__((visibility("default"))) int um_fetch(unsigned long long tag,void*p,unsigned long long n){TRY std::uint64_t h[8]={1,tag,n};sendbytes(h,64);recvbytes(p,n);return 0;END}
extern "C" __attribute__((visibility("default"))) int um_remote(unsigned long long tag,unsigned long long owner,unsigned long long M,unsigned long long N,unsigned long long K,const void*x,void*y){TRY std::uint64_t h[8]={2,tag,M,N,K,2*M*K,2*N*K,owner};sendbytes(h,64);sendbytes(x,2*M*K);recvbytes(y,4*M*N);return 0;END}
extern "C" __attribute__((visibility("default"))) int um_shutdown(){TRY rt->shutdown();logf.flush();InterChiplet::sendCycleCmd(rt->chipCycle());return 0;END}

#include <map>
static std::map<int,int> peer_rd,peer_wr;
extern "C" __attribute__((visibility("default"))) int um_peer_send(int dst,const void*p,unsigned long long n){TRY
 for(unsigned long long off=0;off<n;off+=65536){auto k=std::min<unsigned long long>(65536,n-off);auto path=InterChiplet::sendSync(rank%4,rank/4,dst%4,dst/4);if(!peer_wr.count(dst))peer_wr[dst]=open(path.c_str(),O_WRONLY);io(peer_wr[dst],(char*)p+off,k,true);auto t=InterChiplet::writeSync(rt->chipCycle(),rank%4,rank/4,dst%4,dst/4,k,0);rt->chipCycle()=std::max(rt->chipCycle(),(unsigned long long)t);}return 0;END}
extern "C" __attribute__((visibility("default"))) int um_peer_recv(int src,void*p,unsigned long long n){TRY
 for(unsigned long long off=0;off<n;off+=65536){auto k=std::min<unsigned long long>(65536,n-off);auto path=InterChiplet::receiveSync(src%4,src/4,rank%4,rank/4);if(!peer_rd.count(src))peer_rd[src]=open(path.c_str(),O_RDONLY);io(peer_rd[src],(char*)p+off,k,false);auto t=InterChiplet::readSync(rt->chipCycle(),src%4,src/4,rank%4,rank/4,k,0);rt->chipCycle()=std::max(rt->chipCycle(),(unsigned long long)t);}return 0;END}

#include <array>
static std::vector<unsigned char> local_sram(4194304);
static std::array<unsigned long long,8> bank_free{};
static unsigned long long bank_cycles=0,stream_bytes=0,stream_chunks=0,stream_peak=0;

static void bank_access(unsigned long long a,unsigned long long n){
 if(!n||a+n>local_sram.size())throw std::runtime_error("SRAM bounds");auto begin=rt->chipCycle(),done=begin;
 for(auto line=a/32;line<=(a+n-1)/32;line++){auto b=line%8;auto start=std::max<unsigned long long>(begin,bank_free[b]);bank_free[b]=start+1;done=std::max<unsigned long long>(done,start+1);}bank_cycles+=done-begin;rt->chipCycle()=done;
}
extern "C" __attribute__((visibility("default"))) int um_sram_load(unsigned long long addr,void*out,unsigned long long n){TRY
 for(unsigned long long off=0;off<n;off+=65536){auto k=std::min<unsigned long long>(65536,n-off);rt->load(addr+off,local_sram.data(),k,"HB_to_actual_SRAM");bank_access(0,k);bank_access(0,k);std::memcpy((char*)out+off,local_sram.data(),k);stream_bytes+=k;stream_chunks++;stream_peak=std::max<unsigned long long>(stream_peak,k);}return 0;END}
extern "C" __attribute__((visibility("default"))) int um_bank_challenges(unsigned long long*out){TRY
 auto b=rt->chipCycle(),done=b;
 for(auto a:{0ULL,256ULL}){auto bb=(a/32)%8;auto t=std::max<unsigned long long>(b,bank_free[bb]);bank_free[bb]=t+1;done=std::max(done,t+1);}rt->chipCycle()=done;out[0]=done-b;
 b=rt->chipCycle();done=b;for(auto a:{0ULL,32ULL}){auto bb=(a/32)%8;auto t=std::max<unsigned long long>(b,bank_free[bb]);bank_free[bb]=t+1;done=std::max(done,t+1);}rt->chipCycle()=done;out[1]=done-b;
 b=rt->chipCycle();done=b;for(auto a:{0ULL,256ULL,512ULL})for(auto line=a/32;line<=(a+63)/32;line++){auto bb=line%8;auto t=std::max<unsigned long long>(b,bank_free[bb]);bank_free[bb]=t+1;done=std::max(done,t+1);}rt->chipCycle()=done;out[2]=done-b;return 0;END}
extern "C" __attribute__((visibility("default"))) int um_sram_bad(){try{bank_access(4194304,1);return 0;}catch(const std::exception&){return 1;}}
extern "C" __attribute__((visibility("default"))) int um_sram_finish(){TRY
 std::ofstream f(bank_report+"/SRAM_SUMMARY.json");f<<"{\"array_capacity\":4194304,\"Banks\":8,\"stripe_bytes\":32,\"shared_ports_per_bank\":1,\"bank_service_cycles\":"<<bank_cycles<<",\"read_bytes\":"<<stream_bytes<<",\"write_bytes\":"<<stream_bytes<<",\"chunks\":"<<stream_chunks<<",\"actual_peak_staging_bytes\":"<<stream_peak<<",\"scope\":\"actual HB DMA staging only, not per-MAC or full operator bank costs\"}";return 0;END}

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
static std::ofstream logf,iof;
static void io_stage(unsigned long long n,bool wr,const char*label){if(!n)return;auto start=rt->chipCycle();auto ticks=(n+255)/256;rt->chipCycle()+=ticks;iof<<label<<','<<wr<<','<<n<<','<<start<<','<<rt->chipCycle()<<'\n';}

extern "C" __attribute__((visibility("default"))) const char* um_error(){return error.c_str();}
#define TRY try{
#define END }catch(const std::exception&e){error=e.what();return -1;}
extern "C" __attribute__((visibility("default"))) int um_init(const char*report){TRY NPUSim::NPUConfig c;c.external_memory_enable=true;c.external_memory_model="chiplet";c.dram_transaction_bytes=32;c.dram_size_bytes=536870912;c.dram_chiplet_x=rank%4;c.dram_chiplet_y=8+rank/4;c.dram_chiplet_burst_bytes=65536;c.dram_chiplet_region_bytes=536870912;c.dram_chiplet_grid_cols=4;c.intra_delay_enable=false;c.mac_unit_count=4096;c.sram_per_mac_bytes=1024;c.vector_ops_per_cycle=16;c.reduce_ops_per_cycle=16;c.sram_bandwidth_bytes_per_cycle=256;c.activation_dtype=c.weight_dtype=c.output_dtype=NPUSim::TensorDType::kBf16;c.accumulator_dtype=NPUSim::TensorDType::kFp32;NPUSim::ChipletNpuRuntimeOptions o;o.self_x=rank%4;o.self_y=rank/4;o.report_directory=report;rt=std::make_unique<NPUSim::ChipletNpuRuntime>(c,o);iof.open(std::string(report)+"/IO_SRAM_GATES.csv");iof<<"label,write,bytes,start,complete\n";logf.open(std::string(report)+"/program.csv");logf<<"label,kind,ops,start,complete\n";return 0;END}
extern "C" __attribute__((visibility("default"))) int um_store(unsigned long long addr,const void*p,unsigned long long n){TRY for(unsigned long long off=0;off<n;off+=65536){auto k=std::min<unsigned long long>(65536,n-off);io_stage(k,false,"HB_store_from_IO_SRAM");rt->store(addr+off,(const char*)p+off,k,"actual_tensor_store");}return 0;END}
extern "C" __attribute__((visibility("default"))) int um_load(unsigned long long addr,void*p,unsigned long long n){TRY for(unsigned long long off=0;off<n;off+=65536){auto k=std::min<unsigned long long>(65536,n-off);rt->load(addr+off,(char*)p+off,k,"actual_tensor_load");io_stage(k,true,"HB_load_to_IO_SRAM");}return 0;END}
extern "C" __attribute__((visibility("default"))) int um_compute(unsigned long long ops,int reduce,const char*label){TRY NPUSim::NpuEventRecorder rec;if(reduce)rec.reduceCompute(1,ops);else rec.vectorCompute(1,ops);auto s=rt->scheduleProgram(rec.events());for(auto&e:s.entries)logf<<label<<","<<reduce<<","<<ops<<","<<e.start_cycle<<","<<e.complete_cycle<<"\n";return 0;END}
extern "C" __attribute__((visibility("default"))) unsigned long long um_now(){return rt->chipCycle();}
static void io(int fd,char*p,size_t n,bool wr){if(fd<0)throw std::runtime_error("FIFO open");while(n){auto k=wr?write(fd,p,n):read(fd,p,n);if(k<=0)throw std::runtime_error("FIFO short");p+=k;n-=k;}}

static void sendbytes(const void*p,unsigned long long n){for(unsigned long long off=0;off<n;off+=65536){auto k=std::min<unsigned long long>(65536,n-off);io_stage(k,false,"NoC_send_from_IO_SRAM");auto s=InterChiplet::sendSync(rank%4,rank/4,0,4);if(output_fd<0)output_fd=open(s.c_str(),O_WRONLY);io(output_fd,(char*)p+off,k,true);auto t=InterChiplet::writeSync(rt->chipCycle(),rank%4,rank/4,0,4,k,0);rt->chipCycle()=std::max(rt->chipCycle(),(unsigned long long)t);}}
static void recvbytes(void*p,unsigned long long n){for(unsigned long long off=0;off<n;off+=65536){auto k=std::min<unsigned long long>(65536,n-off);auto s=InterChiplet::receiveSync(0,4,rank%4,rank/4);if(input_fd<0)input_fd=open(s.c_str(),O_RDONLY);io(input_fd,(char*)p+off,k,false);auto t=InterChiplet::readSync(rt->chipCycle(),0,4,rank%4,rank/4,k,0);rt->chipCycle()=std::max(rt->chipCycle(),(unsigned long long)t);io_stage(k,true,"NoC_receive_to_IO_SRAM");}}
extern "C" __attribute__((visibility("default"))) int um_net_recv(void*p,unsigned long long n){TRY recvbytes(p,n);return 0;END}
extern "C" __attribute__((visibility("default"))) int um_net_send(const void*p,unsigned long long n){TRY sendbytes(p,n);return 0;END}
extern "C" __attribute__((visibility("default"))) int um_recv(void*p,unsigned long long n){TRY recvbytes(p,n);return 0;END}
extern "C" __attribute__((visibility("default"))) int um_send(const void*p,unsigned long long n){TRY static std::uint64_t phase=0;std::uint64_t h[8]={3,phase++,n};sendbytes(h,64);sendbytes(p,n);return 0;END}
extern "C" __attribute__((visibility("default"))) int um_fetch(unsigned long long tag,void*p,unsigned long long n){TRY if(n>32ULL*1024*1024)throw std::runtime_error("BF16 weight slot");std::uint64_t h[8]={1,tag,n};sendbytes(h,64);std::vector<char>b(65536);for(unsigned long long off=0;off<n;off+=65536){auto k=std::min<unsigned long long>(65536,n-off);recvbytes(b.data(),k);io_stage(k,false,"BF16_receive_to_HB");rt->store(off,b.data(),k,"streamed_original_BF16_weight");memcpy((char*)p+off,b.data(),k);}return 0;END}
extern "C" __attribute__((visibility("default"))) int um_remote(unsigned long long tag,unsigned long long owner,unsigned long long M,unsigned long long N,unsigned long long K,const void*x,void*y){TRY std::uint64_t h[8]={2,tag,M,N,K,2*M*K,2*N*K,owner};sendbytes(h,64);sendbytes(x,2*M*K);recvbytes(y,4*M*N);return 0;END}
extern "C" __attribute__((visibility("default"))) int um_shutdown(){TRY rt->shutdown();logf.flush();iof.flush();InterChiplet::sendCycleCmd(rt->chipCycle());return 0;END}

#include "sram_matrix.h"
extern "C" __attribute__((visibility("default"))) int um_matrix(unsigned long long x,unsigned long long w,unsigned long long y,unsigned long long M,unsigned long long N,unsigned long long K,unsigned long long job,const char*d){TRY SramMatrix k(*rt);k.run(x,w,y,M,N,K,job,d);return 0;END}
extern "C" __attribute__((visibility("default"))) int um_binary(unsigned long long x,unsigned long long w,unsigned long long y,unsigned long long n,unsigned long long mul,unsigned long long job,const char*d){TRY SramMatrix k(*rt);k.binary(x,w,y,n,mul,job,d);return 0;END}
extern "C" __attribute__((visibility("default"))) int um_software(unsigned long long kind,const void*x,unsigned long long ib,void*y,unsigned long long ob,unsigned long long a,unsigned long long b,unsigned long long c){TRY std::uint64_t h[8]={5,kind,ib,ob,a,b,c};sendbytes(h,64);sendbytes(x,ib);recvbytes(y,ob);return 0;END}

extern "C" __attribute__((visibility("default"))) int um_codec_hb(unsigned long long kind,unsigned long long src,unsigned long long dst,unsigned long long count,void*out){TRY
 if(kind!=1&&kind!=2)throw std::runtime_error("codec kind");auto ib=count*(kind==1?2:4),ob=count*(kind==1?4:2);if(src+ib>536870912ULL||dst+ob>536870912ULL)throw std::runtime_error("codec HB bound");std::uint64_t h[8]={5,kind,ib,ob,count};sendbytes(h,64);std::vector<char>b(65536);
 for(unsigned long long off=0;off<ib;off+=65536){auto k=std::min<unsigned long long>(65536,ib-off);rt->load(src+off,b.data(),k,"BF16_weight_codec_actual_HB_reader");io_stage(k,true,"HB_codec_load_to_IO_SRAM");sendbytes(b.data(),k);}
 for(unsigned long long off=0;off<ob;off+=65536){auto k=std::min<unsigned long long>(65536,ob-off);recvbytes(b.data(),k);io_stage(k,false,"CPU_codec_output_to_HB");rt->store(dst+off,b.data(),k,"CPU_expanded_weight_streamed_HB");memcpy((char*)out+off,b.data(),k);}return 0;END}

extern "C" __attribute__((visibility("default"))) int um_finalize(){TRY
 std::uint64_t h[8]={6,0x51424d4bULL},ack[8];sendbytes(h,64);recvbytes(ack,64);
 if(ack[0]!=6||ack[1]!=h[1]||ack[2]||ack[3]||ack[4]||ack[5]!=(208ULL<<20)||ack[6]||ack[7])throw std::runtime_error("final ownership acknowledgement");
 return 0;END}

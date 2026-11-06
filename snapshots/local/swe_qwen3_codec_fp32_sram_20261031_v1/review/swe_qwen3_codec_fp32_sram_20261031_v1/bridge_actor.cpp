#include <memory>
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
extern "C" __attribute__((visibility("default"))) const char* um_error(){return error.c_str();}
#define TRY try{
#define END }catch(const std::exception&e){error=e.what();return -1;}
extern "C" __attribute__((visibility("default"))) int um_init(const char*report){TRY NPUSim::NPUConfig c;c.external_memory_enable=true;c.external_memory_model="chiplet";c.dram_transaction_bytes=32;c.dram_size_bytes=536870912;c.dram_chiplet_x=rank%4;c.dram_chiplet_y=8+rank/4;c.dram_chiplet_burst_bytes=65536;c.dram_chiplet_region_bytes=536870912;c.dram_chiplet_grid_cols=4;c.intra_delay_enable=false;c.mac_unit_count=4096;c.sram_per_mac_bytes=1024;c.vector_ops_per_cycle=16;c.reduce_ops_per_cycle=16;c.sram_bandwidth_bytes_per_cycle=256;c.activation_dtype=c.weight_dtype=c.output_dtype=NPUSim::TensorDType::kBf16;c.accumulator_dtype=NPUSim::TensorDType::kFp32;NPUSim::ChipletNpuRuntimeOptions o;o.self_x=rank%4;o.self_y=rank/4;o.report_directory=report;rt=std::make_unique<NPUSim::ChipletNpuRuntime>(c,o);logf.open(std::string(report)+"/program.csv");logf<<"label,kind,ops,start,complete\n";return 0;END}
extern "C" __attribute__((visibility("default"))) int um_store(unsigned long long addr,const void*p,unsigned long long n){TRY rt->store(addr,p,n,"actual_tensor_store");return 0;END}
extern "C" __attribute__((visibility("default"))) int um_load(unsigned long long addr,void*p,unsigned long long n){TRY rt->load(addr,p,n,"actual_tensor_load");return 0;END}
extern "C" __attribute__((visibility("default"))) int um_compute(unsigned long long ops,int reduce,const char*label){TRY NPUSim::NpuEventRecorder rec;if(reduce)rec.reduceCompute(1,ops);else rec.vectorCompute(1,ops);auto s=rt->scheduleProgram(rec.events());for(auto&e:s.entries)logf<<label<<","<<reduce<<","<<ops<<","<<e.start_cycle<<","<<e.complete_cycle<<"\n";return 0;END}
extern "C" __attribute__((visibility("default"))) unsigned long long um_now(){return rt->chipCycle();}
static void io(int fd,char*p,size_t n,bool wr){if(fd<0)throw std::runtime_error("FIFO open");while(n){auto k=wr?write(fd,p,n):read(fd,p,n);if(k<=0)throw std::runtime_error("FIFO short");p+=k;n-=k;}}
extern "C" __attribute__((visibility("default"))) int um_recv(void*p,unsigned long long n){TRY auto s=InterChiplet::receiveSync(0,4,rank%4,rank/4);if(input_fd<0)input_fd=open(s.c_str(),O_RDONLY);io(input_fd,(char*)p,n,false);auto t=InterChiplet::readSync(rt->chipCycle(),0,4,rank%4,rank/4,n,0);rt->chipCycle()=std::max(rt->chipCycle(),(unsigned long long)t);return 0;END}
extern "C" __attribute__((visibility("default"))) int um_send(const void*p,unsigned long long n){TRY auto s=InterChiplet::sendSync(rank%4,rank/4,0,4);if(output_fd<0)output_fd=open(s.c_str(),O_WRONLY);io(output_fd,(char*)p,n,true);auto t=InterChiplet::writeSync(rt->chipCycle(),rank%4,rank/4,0,4,n,0);rt->chipCycle()=std::max(rt->chipCycle(),(unsigned long long)t);return 0;END}
extern "C" __attribute__((visibility("default"))) int um_shutdown(){TRY rt->shutdown();logf.flush();InterChiplet::sendCycleCmd(rt->chipCycle());return 0;END}

#include "sram_kernel.h"
extern "C" __attribute__((visibility("default"))) int um_sram_gate(unsigned long long x,unsigned long long w,unsigned long long y,const char*d){TRY ExplicitSramKernel k(*rt,d);k.run(x,w,y,2048,768,d);return 0;END}

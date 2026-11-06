
#include <array>
static std::vector<unsigned char> local_sram(4194304);
static std::array<unsigned long long,8> bank_free{};
static unsigned long long bank_cycles=0,stream_bytes=0,stream_chunks=0,stream_peak=0;
static std::string bank_report;
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

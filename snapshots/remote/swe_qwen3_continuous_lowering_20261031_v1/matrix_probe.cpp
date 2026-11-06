
#include <vector>
#include <cstring>
#include <algorithm>
#include <stdexcept>
namespace NPUSim {
struct Event{unsigned long long n;};struct NpuEventRecorder{std::vector<Event>v;void vectorCompute(int,unsigned long long n){v.push_back({n});}void reduceCompute(int,unsigned long long n){v.push_back({n});}const auto&events(){return v;}};
struct Result{std::vector<int>entries;};
struct ChipletNpuRuntime{unsigned long long now=0;const char*x,*w;char*y;unsigned long long&chipCycle(){return now;}Result scheduleProgram(const std::vector<Event>&e){for(auto v:e)now+=(v.n+15)/16;return {{1}};}void load(unsigned long long a,void*p,unsigned long long n,const char*){const unsigned long long X=320ULL<<20,W=256ULL<<20;if(a>=X)memcpy(p,x+a-X,n);else memcpy(p,w+a-W,n);now+=1;}void store(unsigned long long,void*p,unsigned long long n,const char*){memcpy(y,p,n);now+=1;}};
}
#include "sram_matrix.h"
extern "C" int test(const float*x,const float*w,float*y,int M,int N,int K,const char*d){try{NPUSim::ChipletNpuRuntime r;r.x=(const char*)x;r.w=(const char*)w;r.y=(char*)y;SramMatrix s(r);s.run(320ULL<<20,256ULL<<20,324ULL<<20,M,N,K,1,d);return 0;}catch(...){return -1;}}

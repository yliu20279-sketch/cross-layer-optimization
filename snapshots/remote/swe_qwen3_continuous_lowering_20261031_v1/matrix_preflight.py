import ctypes as C,json,subprocess
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent;B=R.parent
src=r'''
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
'''
(R/'matrix_probe.cpp').write_text(src);subprocess.run(['g++','-O2','-ffp-contract=off','-fno-fast-math','-std=c++17','-shared','-fPIC',str(R/'matrix_probe.cpp'),'-o',str(R/'libmatrix_probe.so')],check=True)
probe=C.CDLL(str(R/'libmatrix_probe.so'));probe.test.argtypes=[C.c_void_p]*3+[C.c_int]*3+[C.c_char_p]
gold=C.CDLL(str(B/'swe_qwen3_step3_four_gates_20261028_v1/libsource_gemm_v2.so'));gold.source_gemm.argtypes=[C.c_void_p]*3+[C.c_int]*3
rng=np.random.default_rng(3102);d=R/'matrix_challenges';d.mkdir(exist_ok=False);results=[]
for M in [1,2,19]:
 for N in [1,17,64,65]:
  for K in [19,20,128,768,2048,4096]:
   xb=(rng.standard_normal((M,K)).astype('<f4').view('<u4')>>16).astype('<u2');wb=(rng.standard_normal((N,K)).astype('<f4').view('<u4')>>16).astype('<u2');xf=(xb.astype('<u4')<<16).view('<f4');wf=(wb.astype('<u4')<<16).view('<f4');actual=np.empty((M,N),dtype='<f4');reference=np.empty_like(actual)
   assert gold.source_gemm(xb.ctypes.data,wb.ctypes.data,reference.ctypes.data,M,N,K)==0
   assert probe.test(xf.ctypes.data,wf.ctypes.data,actual.ctypes.data,M,N,K,str(d).encode())==0
   assert np.array_equal(actual.view('<u4'),reference.view('<u4')),(M,N,K,int(np.count_nonzero(actual!=reference)))
   results.append(dict(M=M,N=N,K=K,elements=M*N))
out=dict(state='PASS_72_FP32_SRAM_NUMERIC_BOUNDARY_CHALLENGES',cases=results,elements=sum(v['elements'] for v in results),scope='same production numeric/SRAM header with in-memory test transport, NOT native timing or full source-matrix execution')
(R/'MATRIX_PREFLIGHT.json').write_text(json.dumps(out,indent=2));print(json.dumps({k:v for k,v in out.items() if k!='cases'}),flush=True)

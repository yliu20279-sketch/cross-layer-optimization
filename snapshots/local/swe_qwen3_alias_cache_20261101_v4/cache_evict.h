#pragma once
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <immintrin.h>
// Explicit software maintenance for the frozen one-active-core, mask-indexed
// LRU hierarchy: 64B lines, L1D8 ways/L2 8 ways/L3 16 ways, 8192 L3 sets.
// This does not claim to implement a native CLFLUSH timing model.
class LruSoftwareMaintenance {
 static constexpr std::uintptr_t LINE=64,SETS=8192,WAYS=33;
 unsigned char*buffer=nullptr;volatile std::uint64_t sink=0;
public:
 LruSoftwareMaintenance(){void*p=nullptr;if(posix_memalign(&p,LINE*SETS,LINE*SETS*WAYS))throw std::runtime_error("eviction buffer allocation");buffer=(unsigned char*)p;std::memset(buffer,0,LINE*SETS*WAYS);}
 ~LruSoftwareMaintenance(){free(buffer);}
 __attribute__((noinline)) void maintain(const void*p,std::size_t bytes){
  if(!bytes)return;auto start=(std::uintptr_t)p/LINE;auto count=(((std::uintptr_t)p%LINE)+bytes+LINE-1)/LINE;if(count>SETS)count=SETS;std::uint64_t sum=0;
  for(std::uintptr_t i=0;i<count;i++){auto set=(start+i)&(SETS-1);for(std::uintptr_t way=0;way<WAYS;way++)sum^=*(volatile std::uint64_t*)(buffer+(way*SETS+set)*LINE);}
  sink=sum;_mm_mfence();
 }
};

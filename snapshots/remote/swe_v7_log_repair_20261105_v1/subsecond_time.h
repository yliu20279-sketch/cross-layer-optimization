#pragma once
#include <cstdint>
using UInt64=uint64_t;using IntPtr=uintptr_t;
struct SubsecondTime{uint64_t v; static SubsecondTime Zero(){return {0};} uint64_t getFS()const{return v;} bool operator>=(SubsecondTime b)const{return v>=b.v;} bool operator>(SubsecondTime b)const{return v>b.v;}};

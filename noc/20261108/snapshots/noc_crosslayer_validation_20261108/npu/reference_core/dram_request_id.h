#pragma once
#include <cstdint>
#include <stdexcept>
namespace NPUSim { namespace RequestId {
constexpr std::uint64_t low_mask=(1ULL<<20)-1;
constexpr std::uint64_t limit=(1ULL<<33)-1;
// Keep all defined protocol flags clear: bits 19:16 and 2:0.
// Legacy sequences retain exactly the same 64-bit ID. Extra sequence bits
// occupy existing unused positions 15:3; no packet field or byte is added.
inline std::uint64_t encode(int x,int y,std::uint64_t sequence){
    if(x<0||x>15||y<0||y>15||!sequence||sequence>limit)
        throw std::runtime_error("invalid DRAM request-id coordinate/sequence");
    return 0x4e50000000000000ULL|(std::uint64_t(x)<<44)|(std::uint64_t(y)<<40)|
           ((sequence&low_mask)<<20)|((sequence>>20)<<3);
}
inline std::uint64_t sequence(std::uint64_t id){return ((id>>20)&low_mask)|(((id>>3)&8191ULL)<<20);}
}}

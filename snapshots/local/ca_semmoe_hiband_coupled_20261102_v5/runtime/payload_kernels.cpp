// Functional CPU payload kernels. No target-cycle or NPU arithmetic claim.
// Build without contraction/fast-math. Existing target primitives stay intact.
#include <cstdint>
#include <cstring>
#include <cmath>
#include <limits>

static float unpack(uint16_t h, int dtype) {
    uint32_t u;
    if (dtype == 1) u = uint32_t(h) << 16; // BF16 is never treated as IEEE FP16.
    else {
        uint32_t sign = uint32_t(h & 0x8000) << 16;
        uint32_t exp = (h >> 10) & 31, mant = h & 1023;
        if (!exp) {
            if (!mant) u = sign;
            else { int e = -14; while (!(mant & 1024)) { mant <<= 1; --e; }
                u = sign | uint32_t(e + 127) << 23 | (mant & 1023) << 13; }
        } else if (exp == 31) u = sign | 0x7f800000 | mant << 13;
        else u = sign | (exp + 112) << 23 | mant << 13;
    }
    float f; std::memcpy(&f, &u, 4); return f;
}
static uint16_t pack(float f, int dtype) {
    uint32_t u; std::memcpy(&u, &f, 4);
    if (dtype == 1) {
        if ((u & 0x7fffffff) > 0x7f800000) return uint16_t((u >> 16) | 0x40);
        return uint16_t((u + 0x7fff + ((u >> 16) & 1)) >> 16);
    }
    uint16_t sign = (u >> 16) & 0x8000;
    int exp = int((u >> 23) & 255) - 127 + 15; uint32_t mant = u & 0x7fffff;
    if (((u >> 23) & 255) == 255) return sign | 0x7c00 | (mant ? 0x200 : 0);
    if (exp >= 31) return sign | 0x7c00;
    if (exp <= 0) {
        if (exp < -10) return sign;
        mant |= 0x800000; int shift = 14 - exp;
        uint32_t value = mant >> shift, rest = mant & ((uint32_t(1) << shift) - 1);
        uint32_t half = uint32_t(1) << (shift - 1);
        value += rest > half || (rest == half && (value & 1));
        return sign | uint16_t(value);
    }
    uint32_t value = (uint32_t(exp) << 10) | (mant >> 13), rest = mant & 8191;
    value += rest > 4096 || (rest == 4096 && (value & 1));
    return sign | uint16_t(value);
}
extern "C" {
int p0_codec(const uint16_t* input, float* output, uint64_t n, int dtype) {
    if (!input || !output || (dtype != 0 && dtype != 1)) return -1;
    for (uint64_t i=0;i<n;++i) output[i]=unpack(input[i],dtype);
    return 0;
}
int p0_round(const float* input, uint16_t* output, uint64_t n, int dtype) {
    if (!input || !output || (dtype != 0 && dtype != 1)) return -1;
    for (uint64_t i=0;i<n;++i) output[i]=pack(input[i],dtype);
    return 0;
}
// FP32 partial dot within consecutive K=64 blocks; FP32 sum of blocks;
// optional bias before final 16-bit store. This is a declared CPU candidate,
// not bit-exact certification against a GPU or the existing target GEMM.
int p0_linear(const uint16_t* a,const uint16_t* b,const uint16_t* bias,
              uint16_t* out,uint64_t m,uint64_t k,uint64_t n,int dtype,int nk) {
    if (!a||!b||!out||!m||!k||!n||(dtype!=0&&dtype!=1)||(nk!=0&&nk!=1)) return -1;
    if (m>SIZE_MAX/k || k>SIZE_MAX/n || m>SIZE_MAX/n) return -2;
    for(uint64_t i=0;i<m;++i) for(uint64_t j=0;j<n;++j) {
        float total=0;
        for(uint64_t begin=0;begin<k;begin+=64) {
            float partial=0;
            for(uint64_t x=begin;x<k&&x<begin+64;++x) {
                float product=unpack(a[i*k+x],dtype)*unpack(b[nk?j*k+x:x*n+j],dtype);
                partial=partial+product;
            }
            total=total+partial;
        }
        if(bias) total=total+unpack(bias[j],dtype);
        out[i*n+j]=pack(total,dtype);
    }
    return 0;
}
// Packets contain exact source bytes. Destination copies occur only at
// completion; the Python transport records the source/destination identities.
int p0_copy(const uint8_t* source,uint8_t* destination,uint64_t n) {
    if(!source||!destination||!n) return -1;
    std::memcpy(destination,source,n); return 0;
}
int p0_sum(const uint16_t* partials,uint16_t* output,uint64_t ranks,uint64_t elements,int dtype) {
    if(!partials||!output||!ranks||!elements||(dtype!=0&&dtype!=1)) return -1;
    for(uint64_t i=0;i<elements;++i) {
        float value=unpack(partials[i],dtype);
        for(uint64_t r=1;r<ranks;++r) value=value+unpack(partials[r*elements+i],dtype);
        output[i]=pack(value,dtype);
    }
    return 0;
}
}

// Wrap the existing, unchanged NPUSim codec; no NPU timing or model execution.
#include "/mnt/sda1/h3240101068/olmoearth_v3_6_integration_20261025_v1/source/NPUSim/npusim_tensor_codec.h"
extern "C" {
void swe_bf16_encode(const float* input, std::uint16_t* output, std::size_t count) {
    for(std::size_t i=0;i<count;++i) output[i]=NPUSim::floatToBf16Bits(input[i]);
}
void swe_bf16_decode(const std::uint16_t* input, float* output, std::size_t count) {
    for(std::size_t i=0;i<count;++i) output[i]=NPUSim::bf16BitsToFloat(input[i]);
}
}

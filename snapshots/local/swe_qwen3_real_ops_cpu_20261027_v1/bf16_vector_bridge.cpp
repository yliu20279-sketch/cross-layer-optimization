// Isolated software lowering candidate: host functional evaluation only.
// No FP16, array throughput assumption, simulator event, or target cycle.
#include "/mnt/sda1/h3240101068/olmoearth_v3_6_integration_20261025_v1/source/NPUSim/npusim_tensor_codec.h"
extern "C" void swe_vector_linear(const std::uint16_t* x,const std::uint16_t* w,
 std::uint16_t* y,std::size_t M,std::size_t N,std::size_t K) {
 for(std::size_t m=0;m<M;++m) for(std::size_t n=0;n<N;++n) {
  float acc=0.0f;
  // K order is fixed across 64-wide software tiles; accumulator not recast BF16.
  for(std::size_t tile=0;tile<K;tile+=64) for(std::size_t k=tile;k<K && k<tile+64;++k) {
   float product=NPUSim::bf16BitsToFloat(x[m*K+k])*NPUSim::bf16BitsToFloat(w[n*K+k]);
   acc=acc+product;
  }
  y[m*N+n]=NPUSim::floatToBf16Bits(acc);
 }
}

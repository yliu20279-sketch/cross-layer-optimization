#include <cmath>
#include <cstddef>
extern "C" void sigmoid_fp32(const float* x,float* y,std::size_t n){
 for(std::size_t i=0;i<n;++i){float e=std::exp(-x[i]);float d=1.0f+e;y[i]=1.0f/d;}
}

#include <cstddef>
extern "C" void sigmoid_finish_fp32(const float* exponent,float* score,std::size_t n){
 for(std::size_t i=0;i<n;++i){float denominator=1.0f+exponent[i];score[i]=1.0f/denominator;}
}

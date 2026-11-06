#include "sim_api.h"
#include <cstdint>
#include <fstream>
#include <memory>
#include <stdexcept>
#include <vector>
extern "C" int full_route128(const std::uint16_t*,float*,std::int64_t*,std::uint16_t*,std::size_t);
int main(int argc,char** argv) {try {
 if(argc!=4)throw std::runtime_error("input ids_out weights_out required");
 std::ifstream input(argv[1],std::ios::binary|std::ios::ate);if(!input)throw std::runtime_error("input open");
 std::size_t bytes=static_cast<std::size_t>(input.tellg());if(bytes%256)throw std::runtime_error("E128 BF16 alignment");
 std::size_t rows=bytes/256;std::vector<std::uint16_t> x(bytes/2);input.seekg(0);input.read(reinterpret_cast<char*>(x.data()),bytes);
 std::unique_ptr<float[]> probability(new float[rows*128]);std::unique_ptr<std::int64_t[]> ids(new std::int64_t[rows*8]);std::unique_ptr<std::uint16_t[]> weights(new std::uint16_t[rows*8]);
 SimRoiStart();int rc=full_route128(x.data(),probability.get(),ids.get(),weights.get(),rows);SimRoiEnd();
 if(rc)throw std::runtime_error("functional domain rejected");
 std::ofstream i(argv[2],std::ios::binary);i.write(reinterpret_cast<const char*>(ids.get()),rows*64);
 std::ofstream w(argv[3],std::ios::binary);w.write(reinterpret_cast<const char*>(weights.get()),rows*16);
 return (!i || !w)?2:0;
 }catch(...){return 1;}}

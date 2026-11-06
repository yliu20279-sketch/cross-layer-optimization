#include "/mnt/sda1/h3240101068/olmoearth_v3_6_integration_20261025_v1/source/NPUSim/npusim_tensor_codec.h"
#include "sim_api.h"
#include <fstream>
#include <iostream>
#include <memory>
#include <vector>
#include <stdexcept>
template<class T> std::vector<T> read(const char* path) {
 std::ifstream f(path,std::ios::binary|std::ios::ate);if(!f)throw std::runtime_error("input open");
 auto size=f.tellg();if(size<0 || size%sizeof(T))throw std::runtime_error("input size");
 std::vector<T> x(static_cast<std::size_t>(size)/sizeof(T));f.seekg(0);f.read(reinterpret_cast<char*>(x.data()),size);return x;
}
template<class T> void write(const char* path,const T* x,std::size_t n) {
 std::ofstream f(path,std::ios::binary);f.write(reinterpret_cast<const char*>(x),n*sizeof(T));if(!f)throw std::runtime_error("output write");
}
int main(int argc,char** argv) {try {
 if(argc!=4)throw std::runtime_error("mode input output required");
 std::string mode=argv[1];
 if(mode=="decode") {
  auto x=read<std::uint16_t>(argv[2]);std::unique_ptr<float[]> y(new float[x.size()]);
  SimRoiStart();
  for(std::size_t i=0;i<x.size();++i)y[i]=NPUSim::bf16BitsToFloat(x[i]);
  SimRoiEnd();write(argv[3],y.get(),x.size());
 } else if(mode=="encode") {
  auto x=read<float>(argv[2]);std::unique_ptr<std::uint16_t[]> y(new std::uint16_t[x.size()]);
  SimRoiStart();
  for(std::size_t i=0;i<x.size();++i)y[i]=NPUSim::floatToBf16Bits(x[i]);
  SimRoiEnd();write(argv[3],y.get(),x.size());
 } else throw std::runtime_error("unknown mode");
 return 0;
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}

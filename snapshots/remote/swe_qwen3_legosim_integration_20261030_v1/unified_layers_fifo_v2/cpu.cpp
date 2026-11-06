#include <fstream>
#include <vector>
#include <stdexcept>
#include "apis_c.h"
#include "sim_api.h"
std::vector<char> load(std::string p){std::ifstream f(p,std::ios::ate|std::ios::binary);auto n=f.tellg();if(n<=0)throw std::runtime_error("input");std::vector<char>a(n);f.seekg(0);f.read(a.data(),n);return a;}
int main(int argc,char**argv){std::string root=argv[1];SimRoiStart();for(auto phase:{"prefill","decode"}){auto x=load(root+"/"+phase+"_input.bin"),g=load(root+"/"+phase+"_gold.bin");if(InterChiplet::sendMessage(1,0,0,0,x.data(),x.size())<0)return 3;std::vector<char>y(g.size());if(InterChiplet::receiveMessage(0,0,1,0,y.data(),y.size())<0)return 4;if(y!=g)return 5;std::ofstream(root+"/"+phase+"_ACTUAL.bin",std::ios::binary).write(y.data(),y.size());}SimRoiEnd();std::ofstream(root+"/CPU_PASS.json")<<"{\"state\":\"PASS_LAYER1_PREFILL_DECODE\"}";return 0;}

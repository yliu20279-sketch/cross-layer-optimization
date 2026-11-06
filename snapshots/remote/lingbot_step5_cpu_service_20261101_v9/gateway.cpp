#include <fcntl.h>
#include <unistd.h>
#include <vector>
#include <map>
#include <string>
#include <fstream>
#include <algorithm>
#include <stdexcept>
#include <cstdint>
#include <iostream>
#include "sync_protocol.h"
class Wire{std::map<int,int>rd,wr;void io(int fd,char*p,size_t n,bool w){while(n){auto k=w?write(fd,p,n):read(fd,p,n);if(k<=0)throw std::runtime_error("FIFO");p+=k;n-=k;}}public:unsigned long long now=1;void receive(int src,void*p,size_t n){for(size_t o=0;o<n;o+=65536){auto k=std::min<size_t>(65536,n-o);auto name=InterChiplet::receiveSync(src%4,src/4,0,4);if(!rd.count(src))rd[src]=open(name.c_str(),O_RDONLY);io(rd[src],(char*)p+o,k,false);now=InterChiplet::readSync(now,src%4,src/4,0,4,k,0);}}void send(int dst,void*p,size_t n){for(size_t o=0;o<n;o+=65536){auto k=std::min<size_t>(65536,n-o);auto name=InterChiplet::sendSync(0,4,dst%4,dst/4);if(!wr.count(dst))wr[dst]=open(name.c_str(),O_WRONLY);io(wr[dst],(char*)p+o,k,true);now=InterChiplet::writeSync(now,0,4,dst%4,dst/4,k,0);}}void forward(int src,int dst,size_t n){std::vector<char>b(65536);for(size_t o=0;o<n;o+=65536){auto k=std::min<size_t>(65536,n-o);receive(src,b.data(),k);send(dst,b.data(),k);}}};
int main(int argc,char**argv){try{Wire w;for(int i=0;i<3;i++){uint64_t h[8];w.receive(0,h,64);if(h[1]!=(unsigned)i)throw std::runtime_error("tag");w.send(48,h,64);for(int j=4;j<8;j++)if(h[j])w.forward(0,48,h[j]);uint64_t r[8];w.receive(48,r,64);if(!std::equal(h,h+8,r))throw std::runtime_error("CPU return descriptor");w.send(0,r,64);w.forward(48,0,h[2]*4);w.forward(48,0,h[2]*2);}InterChiplet::sendCycleCmd(w.now);return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}

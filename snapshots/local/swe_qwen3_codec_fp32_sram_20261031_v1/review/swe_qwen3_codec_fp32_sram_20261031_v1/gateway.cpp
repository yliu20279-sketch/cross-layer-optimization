#include <fcntl.h>
#include <unistd.h>
#include <map>
#include <string>
#include <vector>
#include <stdexcept>
#include <algorithm>
#include <fstream>
#include <cstdlib>
#include "sync_protocol.h"
class Gateway {
 std::map<std::string,int> readfd,writefd;
public:
 unsigned long long now=1;
 void io(int fd,char*p,size_t n,bool wr){if(fd<0)throw std::runtime_error("open FIFO");while(n){auto got=wr?write(fd,p,n):read(fd,p,n);if(got<=0)throw std::runtime_error("short FIFO/EOF");n-=got;p+=got;}}
 void receive(int sx,int sy,void*p,size_t n){auto path=InterChiplet::receiveSync(sx,sy,0,4);if(!readfd.count(path))readfd[path]=open(path.c_str(),O_RDONLY);io(readfd[path],(char*)p,n,false);now=InterChiplet::readSync(now,sx,sy,0,4,n,0);}
 void send(int dx,int dy,const void*p,size_t n){auto path=InterChiplet::sendSync(0,4,dx,dy);if(!writefd.count(path))writefd[path]=open(path.c_str(),O_WRONLY);io(writefd[path],(char*)p,n,true);now=InterChiplet::writeSync(now,0,4,dx,dy,n,0);}
};
int main(int argc,char**argv){try{
 Gateway g;std::vector<char> buf(65536);unsigned long long bytes=0;
 for(int rank=0;rank<1;rank++){
  std::uint64_t h[8];g.receive(0,12,h,sizeof(h));if(h[0]!=(unsigned)rank||h[3]!=2048||h[4]!=768||h[7]!=0x00040003)throw std::runtime_error("descriptor mismatch");
  int x=rank%4,y=rank/4;g.send(x,y,h,sizeof(h));
  for(auto count:{h[6],2*h[6],h[5],2*h[5]})for(std::uint64_t off=0;off<count;off+=buf.size()){
   auto n=std::min<std::uint64_t>(buf.size(),count-off);g.receive(0,12,buf.data(),n);g.send(x,y,buf.data(),n);bytes+=n;
  }
  std::vector<char> result(h[4]*4);g.receive(x,y,result.data(),result.size());g.send(0,12,result.data(),result.size());bytes+=result.size();
 }
 std::ofstream(std::string(argv[1])+"/case"+std::getenv("SWE_RUN_ROUND")+"/GATEWAY_PASS.json")<<"{\"state\":\"PASS_GATEWAY_CPU_EXPANDED_PAYLOADS\",\"payload_bytes\":"<<bytes<<",\"complete_cycle\":"<<g.now<<"}";InterChiplet::sendCycleCmd(g.now);return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}

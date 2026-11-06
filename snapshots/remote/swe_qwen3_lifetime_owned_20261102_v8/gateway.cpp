#include <fcntl.h>
#include <unistd.h>
#include <map>
#include <string>
#include <vector>
#include <stdexcept>
#include <algorithm>
#include <fstream>
#include <cstdlib>
#include <filesystem>
#include "sync_protocol.h"
class Wire {
 std::map<std::string,int> rd,wr;
 void io(int fd,char*p,size_t n,bool write_){if(fd<0)throw std::runtime_error("FIFO open");while(n){auto k=write_?write(fd,p,n):read(fd,p,n);if(k<=0)throw std::runtime_error("short FIFO");p+=k;n-=k;}}
public:
 unsigned long long now=1;
 void receive(int src,void*p,size_t n){for(size_t off=0;off<n;off+=65536){size_t k=std::min<size_t>(65536,n-off);auto path=InterChiplet::receiveSync(src%4,src/4,0,4);if(!rd.count(path))rd[path]=open(path.c_str(),O_RDONLY);io(rd[path],(char*)p+off,k,false);now=InterChiplet::readSync(now,src%4,src/4,0,4,k,0);}}
 void send(int dst,const void*p,size_t n){for(size_t off=0;off<n;off+=65536){size_t k=std::min<size_t>(65536,n-off);auto path=InterChiplet::sendSync(0,4,dst%4,dst/4);if(!wr.count(path))wr[path]=open(path.c_str(),O_WRONLY);io(wr[path],(char*)p+off,k,true);now=InterChiplet::writeSync(now,0,4,dst%4,dst/4,k,0);}}
 void forward(int src,int dst,size_t n){std::vector<char>b(65536);for(size_t off=0;off<n;off+=65536){auto k=std::min<size_t>(65536,n-off);receive(src,b.data(),k);send(dst,b.data(),k);}}
};
int main(int argc,char**argv){try{
 Wire w;unsigned long long jobs=0,fetches=0;std::string out=std::string(argv[1])+"/case"+std::getenv("SWE_RUN_ROUND");
 std::filesystem::create_directories(out);std::ofstream log(out+"/GATEWAY_JOBS.csv");log<<"command,tag,owner,complete\n";
 for(int phase=0;phase<2;phase++){
  std::uint64_t h[8];w.receive(48,h,64);if(h[0]!=4||h[1]!=(unsigned)phase)throw std::runtime_error("input header");w.forward(48,0,h[2]);
  while(true){
   w.receive(0,h,64);w.send(48,h,64);
   if(h[0]==5){w.forward(0,48,h[2]);w.forward(48,0,h[3]);}
   else if(h[0]==1){w.forward(48,0,h[2]);fetches++;log<<1<<','<<h[1]<<",0,"<<w.now<<'\n';}
   else if(h[0]==2){
    auto owner=h[7];if(owner<1||owner>15||h[5]!=2*h[2]*h[4]||h[6]!=2*h[3]*h[4])throw std::runtime_error("matrix descriptor");
    w.forward(0,48,h[5]);w.send(owner,h,64);w.forward(48,owner,h[5]);w.forward(48,owner,2*h[5]);w.forward(48,owner,h[6]);w.forward(48,owner,2*h[6]);
    auto ybytes=4*h[2]*h[3];w.forward(owner,48,ybytes);w.forward(48,0,ybytes);jobs++;log<<2<<','<<h[1]<<','<<owner<<','<<w.now<<'\n';
   }else if(h[0]==3){if(h[1]!=(unsigned)phase)throw std::runtime_error("result phase");w.forward(0,48,h[2]);break;}
   else throw std::runtime_error("unknown root command");
  }
 }
 while(true){
  std::uint64_t h[8];w.receive(0,h,64);
  if(h[0]==6){
   if(h[1]!=0x51424d4bULL)throw std::runtime_error("teardown magic");
   w.send(48,h,64);std::uint64_t ack[8];w.receive(48,ack,64);
   if(ack[0]!=6||ack[1]!=h[1]||ack[2]||ack[3]||ack[4]||ack[5]!=(208ULL<<20)||ack[6]||ack[7])throw std::runtime_error("teardown acknowledgement");
   w.send(0,ack,64);break;
  }
  if(h[0]!=5||(h[1]!=25&&h[1]!=26&&h[1]!=28&&h[1]!=29)||h[2]||h[3]>(128ULL<<20))throw std::runtime_error("invalid post-result command");
  w.send(48,h,64);w.forward(48,0,h[3]);
 }
 std::uint64_t stop[8]={9};for(int i=1;i<16;i++)w.send(i,stop,64);
 std::ofstream(out+"/GATEWAY_PASS.json")<<"{\"state\":\"PASS_FULL_LAYER_SERVICE\",\"remote_jobs\":"<<jobs<<",\"parameter_fetches\":"<<fetches<<",\"complete\":"<<w.now<<"}";InterChiplet::sendCycleCmd(w.now);return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}

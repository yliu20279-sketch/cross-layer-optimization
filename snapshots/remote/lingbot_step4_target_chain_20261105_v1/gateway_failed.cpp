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
#include <cmath>
#include <sys/wait.h>
#include <sys/stat.h>
#include "sync_protocol.h"
class Wire{std::map<int,int>rd,wr;void io(int fd,char*p,size_t n,bool w){while(n){auto k=w?write(fd,p,n):read(fd,p,n);if(k<=0)throw std::runtime_error("FIFO");p+=k;n-=k;}}public:unsigned long long now=1;void receive(int src,void*p,size_t n){for(size_t o=0;o<n;o+=65536){auto k=std::min<size_t>(65536,n-o);auto name=InterChiplet::receiveSync(src%4,src/4,0,4);if(!rd.count(src))rd[src]=open(name.c_str(),O_RDONLY);io(rd[src],(char*)p+o,k,false);now=InterChiplet::readSync(now,src%4,src/4,0,4,k,0);}}void send(int dst,void*p,size_t n){for(size_t o=0;o<n;o+=65536){auto k=std::min<size_t>(65536,n-o);auto name=InterChiplet::sendSync(0,4,dst%4,dst/4);if(!wr.count(dst))wr[dst]=open(name.c_str(),O_WRONLY);io(wr[dst],(char*)p+o,k,true);now=InterChiplet::writeSync(now,0,4,dst%4,dst/4,k,0);}}void dma(size_t bytes,const char*direction,int transaction){
 auto start=now;size_t segments=(bytes+255)/256;
 // Serialized queue 0 is a legal bounded workload of the four-queue model.
 unsigned long long done=start+250+20;
 for(size_t offset=0;offset<bytes;offset+=256)done+=(std::min<size_t>(256,bytes-offset)*100+5503)/5504;
 now=done;
 std::ofstream f("dma_receipts.csv",std::ios::app);
 f<<transaction<<","<<direction<<","<<bytes<<","<<segments<<","<<start<<","<<done<<"\n";
 }
void forward(int src,int dst,size_t n){std::vector<char>b(65536);for(size_t o=0;o<n;o+=65536){auto k=std::min<size_t>(65536,n-o);receive(src,b.data(),k);send(dst,b.data(),k);}}};

int main(int argc,char**argv){try{
 if(argc!=3)throw std::runtime_error("args");std::string root=argv[1],py=argv[2];Wire w;
 for(int op=0;op<2;op++){
  uint64_t h[8];w.receive(0,h,64);if(h[0]!=(uint64_t)op||h[2]>2000000)throw std::runtime_error("descriptor");
  std::string dir=root+"/case"+std::to_string(h[1])+"/service"+std::to_string(op);mkdir(dir.c_str(),0755);
  std::vector<char>data(h[2]);w.receive(0,data.data(),data.size());
  {std::ofstream f(dir+"/input.bin",std::ios::binary);f.write(data.data(),data.size());}
  pid_t pid=fork();if(pid==0){std::string script=root+"/cpu_service.py",tag=std::to_string(op);execl(py.c_str(),py.c_str(),script.c_str(),root.c_str(),dir.c_str(),tag.c_str(),nullptr);_exit(127);}
  int status;waitpid(pid,&status,0);if(!WIFEXITED(status)||WEXITSTATUS(status))throw std::runtime_error("CPU child");
  std::ifstream f(dir+"/output.bin",std::ios::binary|std::ios::ate);auto n=f.tellg();if(n<=0)throw std::runtime_error("output");f.seekg(0);std::vector<char>out((size_t)n);f.read(out.data(),out.size());
  h[3]=out.size();w.send(0,h,64);w.send(0,out.data(),out.size());
 }
 InterChiplet::sendCycleCmd(w.now);return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'
';return 2;}}

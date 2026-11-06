#include <fcntl.h>
#include <unistd.h>
#include <fstream>
#include <vector>
#include <cstring>
#include <stdexcept>
#include "sync_protocol.h"
#include "npusim_tensor_codec.h"
void io(int fd,char*p,size_t n,bool wr){while(n){auto k=wr?write(fd,p,n):read(fd,p,n);if(k<=0)throw std::runtime_error("short FIFO");p+=k;n-=k;}close(fd);}
void send(std::vector<uint16_t>&a,int src,int dst,long t){auto name=InterChiplet::sendSync(src,0,dst,0);int fd=open(name.c_str(),O_WRONLY);if(fd<0)throw std::runtime_error("open send");io(fd,(char*)a.data(),a.size()*2,true);if(InterChiplet::writeSync(t,src,0,dst,0,a.size()*2,0)<0)throw std::runtime_error("write sync");}
void recv(std::vector<uint16_t>&a,int src,int dst,long t){auto name=InterChiplet::receiveSync(src,0,dst,0);int fd=open(name.c_str(),O_RDONLY);if(fd<0)throw std::runtime_error("open recv");io(fd,(char*)a.data(),a.size()*2,false);if(InterChiplet::readSync(t,src,0,dst,0,a.size()*2,0)<0)throw std::runtime_error("read sync");}
int main(int argc,char**argv){bool cpu=std::string(argv[1])=="cpu";std::vector<uint16_t>a;a.push_back(3);for(unsigned i=0;i<65536;++i)if((i&0x7f80)!=0x7f80)a.push_back(i);size_t n=a.size();if(cpu){auto gold=a;send(a,0,1,100);recv(a,1,0,1000);if(a!=gold)return 7;std::ofstream(argv[2])<<"{\"state\":\"PASS_BF16_FIFO_ROUNDTRIP\",\"finite_values\":65280,\"bytes_each_direction\":"<<n*2<<",\"wire_dtype\":3}";}else{a.assign(n,0);recv(a,0,1,100);if(a[0]!=3)return 8;for(size_t i=1;i<n;++i)a[i]=NPUSim::floatToBf16Bits(NPUSim::bf16BitsToFloat(a[i]));send(a,1,0,1000);}InterChiplet::sendCycleCmd(2000);return 0;}

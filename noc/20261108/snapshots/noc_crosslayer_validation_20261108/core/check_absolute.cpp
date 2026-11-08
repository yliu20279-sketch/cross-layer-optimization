#include "net_bench.h"
#include "net_delay.h"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <stdexcept>

static void require(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
int main(int argc,char**argv){
    try{
        require(argc==2,"actual delayInfo input required");
        for(bool enable:{false,true}){
            setenv("LEGOSIM_ABSOLUTE_NOC_COMPLETIONS",enable?"1":"0",1);
            for(long shift:{-50L,0L,100L,100000L}){
                NetworkDelayStruct map;map.loadDelayInfo(argv[1],1,4);
                std::ifstream f(argv[1]);long long ts,s,d,desc,num,sd,rd;std::size_t count=0;
                while(f>>ts>>s>>d>>desc>>num>>sd>>rd){
                    require(num==2&&ts>=50&&sd>=0&&rd>=0,"bad actual fixture");
                    InterChiplet::SyncCommand write{},read{};
                    write.m_src={s%4,s/4};write.m_dst={d%4,d/4};write.m_desc=desc;
                    write.m_cycle=ts+shift;read=write;read.m_cycle=ts+shift+3;
                    auto got=map.getEndCycle(write,read);
                    const double source=enable?std::max<double>(ts+sd,ts+shift):ts+shift+sd;
                    const double receive=enable?std::max<double>({double(ts+rd),double(ts+shift),double(ts+shift+3)}):
                                                std::max<double>(ts+shift+rd,ts+shift+3);
                    require(SRC_DELAY(got)==source&&DST_DELAY(got)==receive,"actual feedback predictor formula mismatch");
                    if(shift==0)require(SRC_DELAY(got)==ts+sd&&DST_DELAY(got)==std::max<double>(ts+rd,ts+3),"fixed-point equivalence failed");
                    ++count;
                }
                require(count>0,"empty actual fixture");
                std::cout<<"PASS enable="<<enable<<" shift="<<shift<<" actual_messages="<<count<<'\n';
            }
        }
        // Explicitly artificial unit inputs: the vertical NPU/R2 namespace and
        // legacy packets must retain the original relative-delay behaviour.
        for(long desc:{long(0x4E50000000000001ULL),long(0x514D000000100001ULL)}){
            const char* path="synthetic_namespace_unit.txt";
            {std::ofstream f(path);f<<"100 0 1 "<<desc<<" 2 10 20\n";}
            NetworkDelayStruct map;map.loadDelayInfo(path,1,4);
            InterChiplet::SyncCommand w{},r{};w.m_src={0,0};w.m_dst={1,0};w.m_desc=desc;w.m_cycle=200;r=w;
            const auto got=map.getEndCycle(w,r);require(SRC_DELAY(got)==210&&DST_DELAY(got)==220,"non-NoC traffic was changed");
        }
        std::cout<<"PASS fixed-point equivalence and vertical/legacy isolation\n";
    }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}

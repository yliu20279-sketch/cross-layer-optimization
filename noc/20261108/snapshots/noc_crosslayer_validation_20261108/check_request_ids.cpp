#include "npu/reference_core/dram_request_id.h"
#include "../Ramulator2-Chiplet/dram_chiplet_protocol.h"
#include "sync_protocol.h"
#include "pipe_comm.h"
#include <array>
#include <iostream>
#include <set>
#include <string>
using NPUSim::RequestId::encode;
void need(bool b,const char*s){if(!b)throw std::runtime_error(s);}
int main(int argc,char**argv){try{
    if(argc==2&&std::string(argv[1])=="--client"){
        InterChiplet::PipeComm pipe;unsigned long long cycle=1;std::array<unsigned char,32> data{},received{};
        const std::uint64_t seqs[]{(1ULL<<20)-2,(1ULL<<20)-1,1ULL<<20,(1ULL<<20)+1,NPUSim::RequestId::limit-1,NPUSim::RequestId::limit};
        for(int i=0;i<6;++i){
            const bool store=i%2==0;const auto id=encode(0,0,seqs[i]);
            DramChiplet::Request request{std::uint64_t(store?1:2),32,4096,id};
            InterChiplet::launchSync(0,0,0,4);
            const auto tx=InterChiplet::sendSync(0,0,0,4);need(pipe.write_data(tx.c_str(),&request,sizeof(request))==32,"request write");
            cycle=InterChiplet::writeSync(cycle,0,0,0,4,32,long(id));
            if(store){
                data.fill(unsigned(i+33));need(pipe.write_data(tx.c_str(),data.data(),32)==32,"payload write");
                cycle=InterChiplet::writeSync(cycle,0,0,0,4,32,long(id));
                DramChiplet::Reply reply{};const auto rx=InterChiplet::receiveSync(0,4,0,0);
                need(pipe.read_data(rx.c_str(),&reply,sizeof(reply))==16,"reply read");
                cycle=InterChiplet::readSync(cycle,0,4,0,0,16,long(id));need(reply.request_id==id&&reply.status==0,"reply ID mismatch");
            }else{
                const auto rx=InterChiplet::receiveSync(0,4,0,0);need(pipe.read_data(rx.c_str(),received.data(),32)==32,"payload read");
                cycle=InterChiplet::readSync(cycle,0,4,0,0,32,long(id));need(received==data,"functional payload changed");
            }
        }
        const auto id=encode(0,0,(1ULL<<20)+8);DramChiplet::Request stop{3,0,0,id};
        InterChiplet::launchSync(0,0,0,4);
        const auto tx=InterChiplet::sendSync(0,0,0,4);need(pipe.write_data(tx.c_str(),&stop,32)==32,"shutdown write");
        cycle=InterChiplet::writeSync(cycle,0,0,0,4,32,long(id));InterChiplet::sendCycleCmd(cycle);
        std::cout<<"PASS native ID-boundary DRAM STORE/LOAD protocol\n";return 0;
    }
    const std::uint64_t values[]{1,2,7,(1ULL<<20)-2,(1ULL<<20)-1,1ULL<<20,(1ULL<<20)+1,(1ULL<<20)+8192,
                                 (1ULL<<32)-1,1ULL<<32,NPUSim::RequestId::limit};
    std::set<std::uint64_t> ids;
    for(int x=0;x<16;++x)for(int y=0;y<16;++y)for(auto sequence:values){
        const auto id=encode(x,y,sequence);need(ids.insert(id).second,"duplicate request ID");
        need(id>>48==0x4e50&&!(id&0xf0007ULL),"magic/flag collision");
        need(((id>>44)&15)==unsigned(x)&&((id>>40)&15)==unsigned(y),"coordinate collision");
        need(NPUSim::RequestId::sequence(id)==sequence,"sequence decode mismatch");
        if(sequence<(1ULL<<20))need(id==(0x4e50000000000000ULL|(std::uint64_t(x)<<44)|(std::uint64_t(y)<<40)|(sequence<<20)),"legacy ID changed");
    }
    for(std::uint64_t sequence=1;sequence<(1ULL<<20)+32;++sequence)
        need(NPUSim::RequestId::sequence(encode(3,3,sequence))==sequence,"dense boundary check failed");
    for(auto sequence:{0ULL,1ULL<<33}){bool rejected=false;try{encode(0,0,sequence);}catch(const std::runtime_error&){rejected=true;}need(rejected,"invalid sequence accepted");}
    std::cout<<"PASS 33-bit ID bijection, defined flags clear, legacy IDs exact, native wrap boundary\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}

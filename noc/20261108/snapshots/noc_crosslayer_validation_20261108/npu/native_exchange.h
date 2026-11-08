#pragma once
#include "native_kernel.h"
#include "ring_local.h"
#include "line_receiver.h"
#include "sync_protocol.h"
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <map>
#include <vector>

// Blocking endpoint program with native source-release and destination-write
// feedback. Transit traffic does not touch a local NPU's SRAM port.
class NativeExchange {
public:
    struct PostedReceive {std::uint64_t op,desc;int source;std::uint64_t bytes,ddr;};
    struct ReceiveVertex {std::uint64_t op,start,finish;};
private:
    struct PendingReceive {PostedReceive spec;std::uint64_t buffer,metadata,prepare,issue;};
    const NPUSim::NPUConfig& cfg_;
    NPUSim::ChipletMemoryClient& memory_;
    int rank_;
    LineReceiver receiver_{STDIN_FILENO};
    std::ostream& ring_events_;
    std::ofstream communication_,service_;
    std::uint64_t port_=0,request_=0;
    std::vector<PendingReceive> batch_;
    bool batch_active_=false;
    std::uint64_t source_buffer_=SOURCE;
    std::ofstream posted_;
    std::ofstream prediction_bounds_;
    bool shared_port_bound_=false;
    static constexpr std::uint64_t INCOMING=1048576,SOURCE=1081344;
    std::uint64_t sync(){
        const auto line=receiver_.next();std::cout<<"[RESPONSE]"<<line;
        const auto reply=InterChiplet::parseCmd(line);
        if(reply.m_type!=InterChiplet::SC_SYNC)throw std::runtime_error("NoC requires native SYNC");
        return static_cast<std::uint64_t>(reply.m_cycle);
    }
    void sram(unsigned long long& cycle,std::uint64_t op,std::uint64_t address,std::uint64_t bytes,bool write){
        if(address+bytes>cfg_.sram_per_mac_bytes)throw std::runtime_error("communication SRAM capacity exceeded");
        NPUSim::NpuEventRecorder recorder;
        if(write)recorder.dmaStore(op+1,address,bytes);else recorder.dmaLoad(op+1,address,bytes);
        auto result=NPUSim::scheduleNpuProgramEvents(recorder.events(),cfg_,cycle,
            [&](const NPUSim::NpuMemoryRequest& r,std::uint64_t issue){
                auto t=std::max(issue,port_);auto left=r.bytes;++request_;
                while(left){auto b=std::min(left,cfg_.sram_bandwidth_bytes_per_cycle);++t;
                    NativeCausalTrace::get().service(t,b);
                    service_<<rank_<<','<<t<<','<<op<<','<<request_<<','<<r.address+r.bytes-left<<','<<b<<','<<r.is_write<<'\n';left-=b;}
                port_=t;return t;
            });
        cycle=std::max<unsigned long long>(cycle,result.overall_finish_cycle);
    }
    void record(const char* role,std::uint64_t op,std::uint64_t desc,int peer,std::uint64_t bytes,
        std::uint64_t buffer,std::uint64_t prepare,std::uint64_t issue,std::uint64_t done,std::uint64_t end){
        communication_<<rank_<<','<<role<<','<<op<<','<<desc<<','<<peer<<','<<bytes<<','<<buffer
            <<','<<prepare<<','<<issue<<','<<done<<','<<end<<'\n';communication_.flush();
    }
public:
    NativeExchange(const NPUSim::NPUConfig& cfg,NPUSim::ChipletMemoryClient& memory,int rank,std::ostream& events):
        cfg_(cfg),memory_(memory),rank_(rank),ring_events_(events),communication_("communication.csv"),service_("exchange_sram_service.csv"),posted_("posted_descriptors.csv"){
        communication_<<"node,role,op,descriptor,peer,bytes,buffer,prepare,issue,done,consume_finish\n";
        service_<<"node,time,op,request,address,bytes,is_write\n";
        posted_<<"node,op,descriptor,peer,bytes,buffer,metadata_address,post_cycle,local_workspace_limit\n";
        const char* floor=std::getenv("LEGOSIM_SHARED_PORT_PREDICTION_BOUND");
        shared_port_bound_=floor&&std::string(floor)=="1";
        if(shared_port_bound_){
            if(!InterChiplet::taggedNocRepliesEnabled())throw std::runtime_error("shared-port prediction bound requires tagged ready protocol");
            prediction_bounds_.open("ring_prediction_bounds.csv");
            prediction_bounds_<<"node,op,phase,step,issue,predicted_join,minimum_join,selected_join,applied\n";
        }
    }
    static std::uint64_t transferTag(std::uint64_t op,int slice,int source,int destination){
        if(op>=(1ULL<<23)||slice<0||slice>=16)throw std::runtime_error("NoC descriptor exceeds declared fields");
        return 0x4E4F800000000000ULL|(op<<24)|(std::uint64_t(slice)<<20)|(std::uint64_t(source)<<8)|destination;
    }
    static std::uint64_t ringTag(int collective,int phase,int step,int source,int destination,int slice=0){
        if(collective<0||collective>=128)throw std::runtime_error("collective descriptor field exceeded");
        if(slice<0||slice>=256)throw std::runtime_error("ring slice descriptor field exceeded");
        return 0x4E4F000000000000ULL|(std::uint64_t(collective)<<40)|(std::uint64_t(slice)<<32)|(std::uint64_t(phase)<<24)
            |(std::uint64_t(step+1)<<20)|(std::uint64_t(source)<<8)|destination;
    }
    void beginBatch(unsigned long long& cycle,const std::vector<PostedReceive>& receives,
                    std::uint64_t local_workspace) {
        if(batch_active_||!batch_.empty()||!InterChiplet::taggedNocRepliesEnabled())
            throw std::runtime_error("invalid nonblocking receive phase");
        // 128 KiB is reserved inside the original 4 MiB SRAM for the finite
        // ready-notice matching table. The data staging block is below it.
        batch_active_=true;source_buffer_=cfg_.sram_per_mac_bytes-131072-32800;
        std::uint64_t cursor=(local_workspace+4095)/4096*4096;
        const auto metadata_begin=source_buffer_-32*receives.size();
        for(std::size_t i=0;i<receives.size();++i){
            const auto& r=receives[i];
            if(!r.bytes||r.bytes>32768||r.bytes%32||cursor+r.bytes>metadata_begin)
                throw std::runtime_error("posted receive payload/descriptor exceeds original SRAM");
            const auto begin=cycle;
            const auto metadata=metadata_begin+i*32;
            // Explicit 32-byte descriptor stored in the existing SRAM. NI
            // fetches it on header retirement, charged by ReceiveContract.
            sram(cycle,r.op,metadata,32,true);
            const auto issue=cycle;
            NativeCausalTrace::get().release(r.desc,false,issue);
            InterChiplet::sendReadCmd(issue,r.source%4,r.source/4,rank_%4,rank_/4,r.bytes,static_cast<long>(r.desc));
            batch_.push_back({r,cursor,metadata,begin,issue});
            posted_<<rank_<<','<<r.op<<','<<r.desc<<','<<r.source<<','<<r.bytes<<','<<cursor
                   <<','<<metadata<<','<<issue<<','<<local_workspace<<'\n';posted_.flush();
            cursor+=r.bytes;
        }
    }
    std::vector<ReceiveVertex> finishBatch(unsigned long long& cycle){
        if(!batch_active_)throw std::runtime_error("no active posted receive phase");
        std::vector<ReceiveVertex> vertices;
        for(const auto& r:batch_){
            const auto before=cycle;
            const auto done=InterChiplet::waitNocCompletion(r.spec.desc,false);
            if(done<r.issue)throw std::runtime_error("receive completion precedes post");
            cycle=std::max<unsigned long long>(cycle,done);
            NativeCausalTrace::get().wait(before,cycle,0,r.spec.desc);
            sram(cycle,r.spec.op,r.buffer,r.spec.bytes,false);
            memory_.storeTrace(r.spec.ddr,r.spec.bytes,"expert_receive_to_DDR");
            record("receive",r.spec.op,r.spec.desc,r.spec.source,r.spec.bytes,r.buffer,r.prepare,r.issue,done,cycle);
            if(vertices.empty()||vertices.back().op!=r.spec.op)vertices.push_back({r.spec.op,r.issue,cycle});
            else vertices.back().finish=cycle;
        }
        batch_.clear();batch_active_=false;source_buffer_=SOURCE;
        return vertices;
    }
    void transfer(unsigned long long& cycle,std::uint64_t op,int source,int destination,
        std::uint64_t bytes,std::uint64_t local_address){
        if(source==destination||(rank_!=source&&rank_!=destination)||!bytes||bytes%32)
            throw std::runtime_error("invalid remote expert transfer");
        for(std::uint64_t offset=0;offset<bytes;offset+=32768){
            const auto count=std::min<std::uint64_t>(32768,bytes-offset);
            const auto desc=transferTag(op,offset/32768,source,destination);
            auto prepare=cycle;
            if(rank_==source){
                memory_.loadTrace(local_address+offset,count,"expert_send_materialize");
                sram(cycle,op,source_buffer_,count+32,true);const auto issue=cycle;
                NativeCausalTrace::get().release(desc,true,issue);
                InterChiplet::sendWriteCmd(issue,source%4,source/4,destination%4,destination/4,count,static_cast<long>(desc));
                const auto done=InterChiplet::taggedNocRepliesEnabled()?InterChiplet::waitNocCompletion(desc,true):sync();
                cycle=std::max<unsigned long long>(cycle,done);
                NativeCausalTrace::get().wait(issue,cycle,desc,0);
                record("send",op,desc,destination,count,source_buffer_,prepare,issue,cycle,cycle);
            }else{
                if(batch_active_)throw std::runtime_error("batch receives must be consumed at phase completion");
                const auto issue=cycle;
                NativeCausalTrace::get().release(desc,false,issue);
                InterChiplet::sendReadCmd(issue,source%4,source/4,destination%4,destination/4,count,static_cast<long>(desc));
                const auto received=InterChiplet::taggedNocRepliesEnabled()?InterChiplet::waitNocCompletion(desc,false):sync();
                cycle=std::max<unsigned long long>(cycle,received);const auto done=cycle;
                NativeCausalTrace::get().wait(issue,cycle,0,desc);
                sram(cycle,op,INCOMING,count,false);
                memory_.storeTrace(local_address+offset,count,"expert_receive_to_DDR");
                record("receive",op,desc,source,count,INCOMING,prepare,issue,done,cycle);
            }
        }
    }
    void ring(unsigned long long& cycle,std::uint64_t op,int collective,const std::string& kind,
        NativeKernel::Region input,NativeKernel::Region output){
        const auto full=kind=="all_gather"?output.second:input.second;
        if(!full||full%524288||full/524288>=256||
            input.second!=(kind=="all_gather"?full/16:full)||
            output.second!=(kind=="reduce_scatter"?full/16:full))
            throw std::runtime_error("streaming ring requires exact 128-token slices");
        for(std::uint64_t slice=0;slice<full/524288;++slice){
        const auto input_bytes=std::uint64_t(kind=="all_gather"?32768:524288);
        const auto output_bytes=std::uint64_t(kind=="reduce_scatter"?32768:524288);
        memory_.loadTrace(input.first+slice*input_bytes,input_bytes,"collective_slice_input_to_SRAM");
        RingLocal local(cfg_,rank_,32768,4096,ring_events_,32800);
        if(kind=="all_gather")local.prepareAllGather(cycle);else local.prepareReduceScatter(cycle);
        const int previous=(rank_+15)%16,next=(rank_+1)%16;
        for(int phase:{0,3}){
            if((phase==0&&kind=="all_gather")||(phase==3&&kind=="reduce_scatter"))continue;
            for(int step=0;step<15;++step){
                const auto begin=cycle;
                const int send=(rank_-step+(phase==0?-1:0)+32)%16;
                const int receive=(rank_-step+(phase==0?-2:-1)+32)%16;
                local.readTransmitChunk(cycle,send,phase,step);
                const auto metadata=cfg_.sram_per_mac_bytes-131072-32800-32;
                sram(cycle,op,metadata,32,true);const auto issue=cycle;
                const auto tx=ringTag(collective,phase,step,rank_,next,slice),rx=ringTag(collective,phase,step,previous,rank_,slice);
                NativeCausalTrace::get().release(tx,true,issue);
                NativeCausalTrace::get().release(rx,false,issue);
                posted_<<rank_<<','<<op<<','<<rx<<','<<previous<<",32768,"<<INCOMING
                       <<','<<metadata<<','<<issue<<",1048576\n";posted_.flush();
                InterChiplet::sendWriteCmd(issue,rank_%4,rank_/4,next%4,next/4,32768,static_cast<long>(tx));
                InterChiplet::sendReadCmd(issue,previous%4,previous/4,rank_%4,rank_/4,32768,static_cast<long>(rx));
                const bool tagged=InterChiplet::taggedNocRepliesEnabled();
                const auto a=tagged?InterChiplet::waitNocCompletion(tx,true):sync();
                const auto b=tagged?InterChiplet::waitNocCompletion(rx,false):sync();
                cycle=std::max(a,b);
                if(shared_port_bound_){
                    // Existing single SRAM port: 1025 source flit reads plus
                    // one incoming descriptor read and 1024 payload writes.
                    // Only impossible cached predictions are constrained.
                    const auto predicted=cycle;
                    const unsigned long long minimum=issue+2ULL*(32768/32+1);
                    cycle=std::max(cycle,minimum);
                    prediction_bounds_<<rank_<<','<<op<<','<<phase<<','<<step<<','<<issue<<','<<predicted<<','<<minimum<<','<<cycle<<','<<(cycle>predicted)<<'\n';
                    prediction_bounds_.flush();
                }
                const auto done=cycle;
                NativeCausalTrace::get().wait(issue,cycle,tx,rx);
                if(phase==0)local.reduceReceivedChunk(cycle,receive,step);else local.copyReceivedChunk(cycle,receive,step);
                record("send",op,tx,next,32768,SOURCE,begin,issue,tagged?a:done,tagged?a:done);
                record("receive",op,rx,previous,32768,INCOMING,begin,issue,tagged?b:done,cycle);
            }
        }
        if(kind!="reduce_scatter")local.unpackAllGather(cycle);
        local.readResult(cycle,kind=="reduce_scatter");
        memory_.storeTrace(output.first+slice*output_bytes,output_bytes,"collective_slice_result_to_DDR");
        }
    }
};

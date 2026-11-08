#pragma once
#include "npusim_runtime.h"
#include "causal_trace.h"
#include <algorithm>
#include <cstdint>
#include <ostream>
#include <stdexcept>
#include <string>
#include <cstdlib>
#include <fstream>
#include <set>

// Local lowering for an explicitly buffered, step-synchronous ring.
// DMA-shaped generic events use an SRAM callback, NOT ChipletMemoryClient.
// The original NPUSim scheduler owns dependencies and vector/DMA resources.
class RingLocal {
    NPUSim::NPUConfig config_;
    std::ostream& log_;
    int rank_;
    std::uint64_t chunk_, total_, token_, tokens_, ready_=0, sequence_=0;
    std::uint64_t read_=0, write_=0, adds_=0, source_pool_=0;
    std::uint64_t port_ready_=0,request_=0;
    std::set<std::uint64_t> noc_busy_;
    std::ofstream service_;
    std::uint64_t packed()const{return total_;}
    std::uint64_t incoming()const{return 2*total_;}
    std::uint64_t chunkAddress(int c)const{
        if(c<0||c>=16)throw std::runtime_error("chunk outside ring");
        return packed()+static_cast<std::uint64_t>(c)*chunk_;
    }
    void execute(const NPUSim::NpuEventRecorder& recorder, unsigned long long& cycle,
                 const std::string& label) {
        if(cycle<ready_)throw std::runtime_error("overlapping local kernel without dependency");
        const auto result=NPUSim::scheduleNpuProgramEvents(recorder.events(),config_,cycle,
            [&](const NPUSim::NpuMemoryRequest& req,std::uint64_t issue){
                if(req.address>footprint()||req.bytes>footprint()-req.address)
                    throw std::runtime_error("local SRAM address out of allocation");
                (req.is_write?write_:read_)+=req.bytes;
                // One conservative shared port: actual NoC accesses have fixed
                // priority. A NoC access occupies the edge, even for 32 bytes.
                // These are previous *measured simulator service edges*, never
                // predicted latencies. Accept performance only at a fixed point.
                auto left=req.bytes;auto t=std::max(issue,port_ready_);
                ++request_;
                while(left){
                    // This actor already waits for BOTH source-release and
                    // destination-write completions before any local kernel,
                    // and posts the next READ only after its local kernel.
                    // NI cannot use this node's SRAM during the local interval
                    // at a message fixed point. Check that same-round fact;
                    // do not add stale absolute NoC reservations here.
                    ++t;
                    const auto bytes=std::min(left,config_.sram_bandwidth_bytes_per_cycle);
                    NativeCausalTrace::get().service(t,bytes);
                    service_<<rank_<<','<<t<<','<<label<<','<<request_<<','
                        <<req.address+(req.bytes-left)<<','<<bytes<<','<<req.is_write<<'\n';
                    left-=bytes;
                }
                port_ready_=t;return t;
            });
        for(const auto& entry:result.entries){
            const auto& e=entry.event;
            const char* kind=e.kind==NPUSim::NpuProgramEventKind::kDmaLoad?"sram_read":
                e.kind==NPUSim::NpuProgramEventKind::kDmaStore?"sram_write":
                e.kind==NPUSim::NpuProgramEventKind::kVectorCompute?"vector_add":"barrier";
            if(e.kind==NPUSim::NpuProgramEventKind::kVectorCompute)adds_+=e.ops;
            if(entry.complete_cycle<entry.start_cycle)throw std::runtime_error("bad event time");
            log_<<rank_<<','<<label<<','<<e.id<<','<<kind<<','<<e.address<<','<<e.bytes<<','<<e.ops
                <<','<<entry.issue_cycle<<','<<entry.start_cycle<<','<<entry.complete_cycle<<'\n';
        }
        cycle=std::max<unsigned long long>(cycle,result.finish_cycle);ready_=cycle;++sequence_;
    }
    void copyLayout(unsigned long long& cycle,bool pack){
        NPUSim::NpuEventRecorder r;NPUSim::NpuEventId previous=0;
        for(std::uint64_t t=0;t<tokens_;++t){
            const auto raw=t*token_;
            const auto ordered=packed()+(t%16)*chunk_+(t/16)*token_;
            const auto load=r.dmaLoad(600000+sequence_,pack?raw:ordered,token_,
                previous?std::vector<NPUSim::NpuEventId>{previous}:std::vector<NPUSim::NpuEventId>{});
            previous=r.dmaStore(600000+sequence_,pack?ordered:raw,token_,{load});
        }
        execute(r,cycle,pack?"pack_token_chunks":"unpack_token_chunks");
    }
public:
    RingLocal(const NPUSim::NPUConfig& config,int rank,std::uint64_t chunk_bytes,
              std::uint64_t token_bytes,std::ostream& log,std::uint64_t source_pool_bytes=0):
        config_(config),log_(log),rank_(rank),chunk_(chunk_bytes),total_(16*chunk_bytes),
        token_(token_bytes),tokens_(token_bytes?16*chunk_bytes/token_bytes:0),source_pool_(source_pool_bytes){
        if(rank<0||rank>=16||!chunk_||!token_||chunk_%token_||chunk_%2||
           !config_.sram_bandwidth_bytes_per_cycle||!config_.vector_ops_per_cycle)
            throw std::runtime_error("invalid ring local configuration");
        if(config_.activation_bytes!=2||config_.activation_dtype!=NPUSim::TensorDType::kBf16)
            throw std::runtime_error("local ring requires explicit bf16 activation format");
        if(config_.mac_unit_count!=1||footprint()>config_.sram_per_mac_bytes)
            throw std::runtime_error("collective working set does not fit target single-array SRAM");
        if(source_pool_&&source_pool_<chunk_+32)throw std::runtime_error("source staging too small for header plus chunk");
        const char*dir=std::getenv("NPU_SRAM_NOC_PROFILE");
        if(!dir)throw std::runtime_error("explicit NoC port profile directory required, including cold empty profile");
        std::ifstream input(std::string(dir)+"/node_"+std::to_string(rank_)+".txt");
        if(!input)throw std::runtime_error("missing actual NoC port profile");
        std::uint64_t edge;while(input>>edge){
            if(!edge||!noc_busy_.insert(edge).second)throw std::runtime_error("invalid/duplicate NoC service edge");
        }
        if(!input.eof())throw std::runtime_error("bad NoC port profile");
        const bool exists=std::ifstream("sram_service.csv").good();
        service_.open("sram_service.csv",std::ios::app);
        if(!service_)throw std::runtime_error("cannot open SRAM service log");
        if(!exists)service_<<"node,time,label,request,address,bytes,is_write\n";
    }
    std::uint64_t footprint()const{return 2*total_+chunk_+source_pool_;}
    std::uint64_t readBytes()const{return read_;}
    std::uint64_t writeBytes()const{return write_;}
    std::uint64_t addElements()const{return adds_;}
    void prepareReduceScatter(unsigned long long& cycle){
        // Charge materialising the producer's complete partial output, then
        // explicitly pack interleaved token ownership into contiguous chunks.
        NPUSim::NpuEventRecorder r;r.dmaStore(600000+sequence_,0,total_);
        execute(r,cycle,"materialize_partial_output");copyLayout(cycle,true);
    }
    void prepareAllGather(unsigned long long& cycle){
        NPUSim::NpuEventRecorder r;r.dmaStore(600000+sequence_,chunkAddress(rank_),chunk_);
        execute(r,cycle,"materialize_owned_chunk");
    }
    void readTransmitChunk(unsigned long long& cycle,int chunk,int phase,int step){
        NPUSim::NpuEventRecorder r;const auto read=r.dmaLoad(600000+sequence_,chunkAddress(chunk),chunk_);
        if(source_pool_)r.dmaStore(600000+sequence_,2*total_+chunk_,chunk_+32,{read});
        execute(r,cycle,"tx_read_p"+std::to_string(phase)+"_s"+std::to_string(step));
    }
    void reduceReceivedChunk(unsigned long long& cycle,int chunk,int step){
        NPUSim::NpuEventRecorder r;
        const auto a=r.dmaLoad(600000+sequence_,chunkAddress(chunk),chunk_);
        const auto b=r.dmaLoad(600000+sequence_,incoming(),chunk_);
        const auto add=r.vectorCompute(600000+sequence_,chunk_/2,{a,b});
        r.dmaStore(600000+sequence_,chunkAddress(chunk),chunk_,{add});
        execute(r,cycle,"rs_reduce_s"+std::to_string(step));
    }
    void copyReceivedChunk(unsigned long long& cycle,int chunk,int step){
        NPUSim::NpuEventRecorder r;
        const auto input=r.dmaLoad(600000+sequence_,incoming(),chunk_);
        r.dmaStore(600000+sequence_,chunkAddress(chunk),chunk_,{input});
        execute(r,cycle,"ag_copy_s"+std::to_string(step));
    }
    void unpackAllGather(unsigned long long& cycle){copyLayout(cycle,false);}
    void readResult(unsigned long long& cycle,bool owned_only){
        NPUSim::NpuEventRecorder r;
        r.dmaLoad(600000+sequence_,owned_only?chunkAddress(rank_):0,owned_only?chunk_:total_);
        execute(r,cycle,"result_read_to_DDR");
    }
};

#pragma once
#include "npusim_chiplet_memory.h"
#include "causal_trace.h"
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <ostream>
#include <set>
#include <stdexcept>
#include <utility>
#include <vector>

// Explicit materialised kernels: native DDR callbacks, SRAM service edges,
// and native vector/reduce resources. No measured GPU time is substituted.
class NativeKernel {
public:
    using Region=std::pair<std::uint64_t,std::uint64_t>;
private:
    const NPUSim::NPUConfig& cfg_;
    NPUSim::ChipletMemoryClient& memory_;
    std::ostream& events_;
    std::ofstream service_;
    int rank_;
    std::uint64_t ready_=0,serial_=0;
    static constexpr std::uint64_t LOCAL=1ULL<<63;
public:
    NativeKernel(const NPUSim::NPUConfig& cfg,NPUSim::ChipletMemoryClient& memory,
        int rank,std::ostream& events):cfg_(cfg),memory_(memory),events_(events),
        service_("kernel_sram_service.csv"),rank_(rank){
        if(!service_)throw std::runtime_error("kernel SRAM log unavailable");
        service_<<"node,time,op,request,address,bytes,is_write\n";
    }
    void runRows(unsigned long long& cycle,std::uint64_t op,
        const std::vector<Region>& inputs,const std::vector<Region>& outputs,
        std::uint64_t vector_ops,std::uint64_t reduce_ops,std::uint64_t rows,
        const std::vector<std::uint64_t>& input_rows){
        std::uint64_t footprint=0;
        for(const auto& r:std::set<Region>(inputs.begin(),inputs.end()))footprint+=(r.second+31)/32*32;
        for(const auto& r:outputs)footprint+=(r.second+31)/32*32;
        if(footprint<=cfg_.sram_per_mac_bytes){run(cycle,op,inputs,outputs,vector_ops,reduce_ops);return;}
        if(!rows||inputs.size()!=input_rows.size()||vector_ops%rows||reduce_ops%rows)
            throw std::runtime_error("row-kernel streaming contract is not divisible");
        for(std::uint64_t begin=0;begin<rows;){
            auto count=std::min<std::uint64_t>(64,rows-begin);
            for(auto r:input_rows)if(r>1){
                if(rows%r)throw std::runtime_error("unsupported row broadcast");
                count=std::min(count,r-begin%r);
            }
            std::vector<Region> in,out;
            for(std::size_t i=0;i<inputs.size();++i){
                const auto& r=inputs[i];const auto m=input_rows[i];
                if(!m||r.second%m)throw std::runtime_error("non-contiguous row operand");
                const auto width=r.second/m;
                in.push_back(m==1?r:Region{r.first+(begin%m)*width,count*width});
            }
            for(const auto& r:outputs){
                if(r.second%rows)throw std::runtime_error("non-contiguous output rows");
                const auto width=r.second/rows;out.push_back({r.first+begin*width,count*width});
            }
            run(cycle,op,in,out,vector_ops/rows*count,reduce_ops/rows*count);begin+=count;
        }
    }
    void run(unsigned long long& cycle,std::uint64_t op,
        const std::vector<Region>& inputs,const std::vector<Region>& outputs,
        std::uint64_t vector_ops,std::uint64_t reduce_ops){
        NPUSim::NpuEventRecorder recorder;std::uint64_t cursor=0;
        std::vector<NPUSim::NpuEventId> reads;
        std::set<Region> unique(inputs.begin(),inputs.end());
        for(const auto& [address,bytes]:unique){
            if(!bytes)continue;
            if(address==0||address>cfg_.dram_size_bytes||bytes>cfg_.dram_size_bytes-address)
                throw std::runtime_error("kernel input outside physical DDR");
            auto load=recorder.dmaLoad(op+1,address,bytes);
            auto put=recorder.dmaStore(LOCAL|op,cursor,bytes,{load});
            reads.push_back(recorder.dmaLoad(LOCAL|op,cursor,bytes,{put}));
            cursor=(cursor+bytes+31)/32*32;
        }
        auto previous=recorder.barrier(op+1,reads);
        if(vector_ops)previous=recorder.vectorCompute(op+1,vector_ops,{previous});
        if(reduce_ops)previous=recorder.reduceCompute(op+1,reduce_ops,{previous});
        for(const auto& [address,bytes]:outputs){
            if(!bytes)continue;
            if(address==0||address>cfg_.dram_size_bytes||bytes>cfg_.dram_size_bytes-address)
                throw std::runtime_error("kernel output outside physical DDR");
            auto put=recorder.dmaStore(LOCAL|op,cursor,bytes,{previous});
            auto take=recorder.dmaLoad(LOCAL|op,cursor,bytes,{put});
            recorder.dmaStore(op+1,address,bytes,{take});
            cursor=(cursor+bytes+31)/32*32;
        }
        if(cursor>cfg_.sram_per_mac_bytes)
            throw std::runtime_error("materialised native kernel exceeds unchanged SRAM; needs explicit tiling");
        NPUSim::ChipletDmaCallbackOptions options;options.gate_on_external_completion=true;
        auto ddr=memory_.makeTraceDmaCallback(options);
        auto result=NPUSim::scheduleNpuProgramEvents(recorder.events(),cfg_,cycle,
            [&](const NPUSim::NpuMemoryRequest& r,std::uint64_t issue){
                if(!(r.op_desc&LOCAL))return ddr(r,issue);
                auto t=std::max(issue,ready_);auto remaining=r.bytes;++serial_;
                while(remaining){
                    auto b=std::min(remaining,cfg_.sram_bandwidth_bytes_per_cycle);++t;
                    NativeCausalTrace::get().service(t,b);
                    service_<<rank_<<','<<t<<','<<op<<','<<serial_<<','
                        <<r.address+(r.bytes-remaining)<<','<<b<<','<<r.is_write<<'\n';
                    remaining-=b;
                }
                ready_=t;return t;
            });
        for(const auto& e:result.entries)
            events_<<rank_<<','<<op<<','<<static_cast<int>(e.event.kind)<<','<<e.event.address
                <<','<<e.event.bytes<<','<<e.event.ops<<','<<e.issue_cycle<<','<<e.start_cycle<<','<<e.complete_cycle<<'\n';
        cycle=std::max<unsigned long long>(cycle,result.overall_finish_cycle);
    }
};

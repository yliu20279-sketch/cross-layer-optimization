#pragma once
#include "npusim_chiplet_memory.h"
#include "causal_trace.h"
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

// Common tile-major kernel layout for every NoC configuration. Packing is a
// permutation, not new input data. Runtime activation packing/unpacking issues
// real DRAM and SRAM events; static weights are compiled in packed order.
class NativePackedLinear {
    struct Tile {std::uint64_t m,n,k,mt,nt,kt;bool last;};
    static void local(const NPUSim::NPUConfig& cfg,unsigned long long& cycle,
        std::uint64_t bytes,std::uint64_t label){
        if(2*bytes>cfg.sram_per_mac_bytes)throw std::runtime_error("packing buffers exceed original SRAM");
        const bool exists=std::ifstream("packing_sram_service.csv").good();
        std::ofstream service("packing_sram_service.csv",std::ios::app);
        if(!exists)service<<"time,op,request,address,bytes,is_write\n";
        static std::uint64_t request=0;
        NPUSim::NpuEventRecorder r;
        auto put=r.dmaStore(label,0,bytes);
        auto read=r.dmaLoad(label,0,bytes,{put});
        auto packed=r.dmaStore(label,bytes,bytes,{read});
        r.dmaLoad(label,bytes,bytes,{packed});
        auto result=NPUSim::scheduleNpuProgramEvents(r.events(),cfg,cycle,
            [&](const NPUSim::NpuMemoryRequest& req,std::uint64_t issue){
                auto t=issue,remaining=req.bytes;++request;
                while(remaining){const auto b=std::min(remaining,cfg.sram_bandwidth_bytes_per_cycle);++t;
                    NativeCausalTrace::get().service(t,b);
                    service<<t<<','<<label<<','<<request<<','<<req.address+req.bytes-remaining<<','<<b<<','<<req.is_write<<'\n';remaining-=b;}
                return t;
            });
        cycle=std::max<unsigned long long>(cycle,result.overall_finish_cycle);
    }
    static std::uint64_t env(const char* name){
        const char* p=std::getenv(name);if(!p)throw std::runtime_error(std::string("missing physical packed allocation ")+name);
        return std::stoull(p);
    }
    static void packRows(const NPUSim::NPUConfig& cfg,NPUSim::ChipletMemoryClient& memory,
        unsigned long long& cycle,std::uint64_t M,std::uint64_t K,std::uint64_t source,std::uint64_t destination,bool unpack){
        for(std::uint64_t m=0;m<M;m+=64){
            const auto count=std::min<std::uint64_t>(64,M-m)*K*2;
            memory.loadTrace(source+m*K*2,count,unpack?"unpack_C_read_packed":"pack_A_read_rows");
            local(cfg,cycle,count,unpack?900002:900001);
            memory.storeTrace(destination+m*K*2,count,unpack?"unpack_C_write_rows":"pack_A_write_tiles");
        }
    }
public:
    static NPUSim::NpuTileScheduleResult run(const NPUSim::NPUConfig& cfg,NPUSim::ChipletMemoryClient& memory,
        unsigned long long& cycle,std::uint64_t M,std::uint64_t K,std::uint64_t N,
        std::uint64_t input,std::uint64_t weight,std::uint64_t output,std::ostream& log,
        bool rhs_stored_transposed=true,bool static_weight_prepacked=false,
        std::ostream* mac_events=nullptr,std::uint64_t graph_op=0){
        if(cfg.mac_unit_count!=1||cfg.tile_m!=64||cfg.tile_n!=64||cfg.tile_k!=64||
            cfg.activation_bytes!=2||cfg.weight_bytes!=2||cfg.output_bytes!=2)
            throw std::runtime_error("packed kernel requires unchanged bf16 target tiling");
        const auto base=env("NPU_PACKING_BASE"),capacity=env("NPU_PACKING_CAPACITY");
        if(base+3*capacity>cfg.dram_size_bytes||M*K*2>capacity||M*N*2>capacity||
            (!static_weight_prepacked&&N*K*2>capacity))throw std::runtime_error("packed DDR scratch allocation overflow");
        const auto A=base,B=base+capacity,C=base+2*capacity;
        packRows(cfg,memory,cycle,M,K,input,A,false);
        if(!static_weight_prepacked){
            // QK's K-cache is stored [N,K]; SV's V-cache is [K,N]. Both
            // are permuted to the same [n-tile,k-tile,nt,kt] packed order.
            memory.loadTrace(weight,N*K*2,rhs_stored_transposed?"pack_attention_K_read":"pack_attention_V_read");
            local(cfg,cycle,N*K*2,900003);
            memory.storeTrace(B,N*K*2,"pack_attention_RHS_write_tiles");
        }
        const auto W=static_weight_prepacked?weight:B;
        auto plan=NPUSim::planMatMulTiles(M,K,N,cfg);std::vector<Tile> tiles;
        for(std::uint64_t m=0;m<M;m+=64)for(std::uint64_t n=0;n<N;n+=64)for(std::uint64_t k=0;k<K;k+=64)
            tiles.push_back({m,n,k,std::min<std::uint64_t>(64,M-m),std::min<std::uint64_t>(64,N-n),
                std::min<std::uint64_t>(64,K-k),k+64>=K});
        if(tiles.size()!=plan.size())throw std::runtime_error("canonical packed tile order differs");
        std::uint64_t ops=0,reads=0,writes=0,segments=0;
        for(std::size_t i=0;i<tiles.size();++i){
            const auto& t=tiles[i];const auto& native=plan[i];
            if(native.tile_id!=i+1||native.ops!=2*t.mt*t.nt*t.kt||
                native.ddr_read_bytes!=2*(t.mt*t.kt+t.nt*t.kt)||
                native.ddr_write_bytes!=(t.last?2*t.mt*t.nt:0))throw std::runtime_error("packed tile/native byte contract mismatch");
            ops+=native.ops;
        }
        if(ops!=2*M*K*N)throw std::runtime_error("packed native operation total mismatch");
        NPUSim::ChipletDmaCallbackOptions options;options.gate_on_external_completion=true;
        auto transfer=memory.makeTraceDmaCallback(options);
        log<<"tile,is_write,address,bytes,issue,complete\n";
        auto result=NPUSim::scheduleNpuTileEvents(plan,cfg,cycle,0,
            [&](const NPUSim::NpuMemoryRequest& req,std::uint64_t issue){
                if(req.tile_id==0||req.tile_id>tiles.size())throw std::runtime_error("bad packed native tile ID");
                const auto& t=tiles[req.tile_id-1];auto done=issue;std::uint64_t count=0;
                auto segment=[&](std::uint64_t address,std::uint64_t bytes){
                    if(address==0||address>cfg.dram_size_bytes||bytes>cfg.dram_size_bytes-address)
                        throw std::runtime_error("packed physical DMA out of bounds");
                    auto part=req;part.address=address;part.bytes=bytes;const auto begin=done;
                    done=transfer(part,done);if(done<begin)throw std::runtime_error("packed DRAM completed before issue");
                    log<<req.tile_id<<','<<req.is_write<<','<<address<<','<<bytes<<','<<begin<<','<<done<<'\n';
                    count+=bytes;++segments;
                };
                if(req.is_write){
                    if(req.bytes)segment(C+2*(t.m*N+t.n*t.mt),2*t.mt*t.nt);
                    writes+=count;
                }else{
                    segment(A+2*(t.m*K+t.k*t.mt),2*t.mt*t.kt);
                    segment(W+2*(t.n*K+t.k*t.nt),2*t.nt*t.kt);reads+=count;
                }
                if(count!=req.bytes)throw std::runtime_error("packed DMA did not conserve native bytes");
                return done;
            });
        // Read-only observer: these are native scheduler entries, not a
        // reconstructed MAC-rate estimate or added execution events.
        if(mac_events)for(const auto& e:result.entries)
            *mac_events<<graph_op<<','<<e.tile.tile_id<<','<<e.tile.mac_id<<','<<e.tile.ops
                <<','<<e.read_issue_cycle<<','<<e.data_ready_cycle<<','<<e.mac_start_cycle
                <<','<<e.mac_finish_cycle<<','<<e.write_issue_cycle<<','<<e.write_complete_cycle
                <<','<<e.tile.compute_cycles<<','<<e.tile.local_memory_cycles<<'\n';
        cycle=std::max<unsigned long long>(cycle,result.overall_finish_cycle);
        packRows(cfg,memory,cycle,M,N,C,output,true);
        std::cout<<"[NATIVE_PACKED_LINEAR] "<<M<<' '<<K<<' '<<N<<' '<<tiles.size()<<' '<<ops<<' '
            <<reads<<' '<<writes<<' '<<segments<<' '<<cycle<<std::endl;
        return result;
    }
};

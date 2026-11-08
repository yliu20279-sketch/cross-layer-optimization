#pragma once
#include "npusim_chiplet_memory.h"
#include <algorithm>
#include <cstdint>
#include <functional>
#include <iostream>
#include <ostream>
#include <stdexcept>
#include <vector>

// Uses the existing canonical NPUSim tile planner/scheduler. The adapter only
// maps its aggregate A/B/C bytes onto actual row-major tensor addresses.
// W is stored [N,K], so mathematical B is transpose(W); no new timing formula.
class NativeLinear {
    struct Tile {std::uint64_t m,n,k,mt,nt,kt;bool last;};
public:
    static NPUSim::NpuTileScheduleResult run(const NPUSim::NPUConfig& cfg,
        NPUSim::ChipletMemoryClient& mem,unsigned long long& cycle,
        std::uint64_t M,std::uint64_t K,std::uint64_t N,
        std::uint64_t input,std::uint64_t weight,std::uint64_t output,std::ostream& log,
        bool weight_stored_transposed=true){
        if(cfg.mac_unit_count!=1||cfg.tile_m!=64||cfg.tile_n!=64||cfg.tile_k!=64)
            throw std::runtime_error("native linear requires unchanged target 64x64x64 single-array tiling");
        auto plan=NPUSim::planMatMulTiles(M,K,N,cfg);std::vector<Tile> mapping;
        for(std::uint64_t m=0;m<M;m+=64)for(std::uint64_t n=0;n<N;n+=64)for(std::uint64_t k=0;k<K;k+=64)
            mapping.push_back({m,n,k,std::min<std::uint64_t>(64,M-m),std::min<std::uint64_t>(64,N-n),
                std::min<std::uint64_t>(64,K-k),k+64>=K});
        if(plan.size()!=mapping.size())throw std::runtime_error("native tile order/count differs from address mapping");
        std::uint64_t ops=0;
        for(std::size_t i=0;i<plan.size();++i){auto&t=plan[i];const auto&a=mapping[i];
            if(t.tile_id!=i+1||t.ops!=2*a.mt*a.nt*a.kt||t.ddr_read_bytes!=(a.mt*a.kt*cfg.activation_bytes+a.kt*a.nt*cfg.weight_bytes)||
               t.ddr_write_bytes!=(a.last?a.mt*a.nt*cfg.output_bytes:0))
                throw std::runtime_error("native tile bytes/ops do not match exact tensor slice");
            ops+=t.ops;
        }
        if(ops!=2*M*K*N)throw std::runtime_error("native operation total mismatch");
        NPUSim::ChipletDmaCallbackOptions options;options.gate_on_external_completion=true;
        auto transfer=mem.makeTraceDmaCallback(options);
        std::uint64_t read_bytes=0,write_bytes=0,segments=0;
        log<<"tile,is_write,address,bytes,issue,complete\n";
        auto cb=[&](const NPUSim::NpuMemoryRequest& request,std::uint64_t issue){
            if(!request.tile_id||request.tile_id>mapping.size())throw std::runtime_error("unknown native tile in DMA callback");
            const auto&a=mapping[request.tile_id-1];auto t=issue;std::uint64_t bytes=0;
            auto segment=[&](std::uint64_t address,std::uint64_t size){
                if(address>cfg.dram_size_bytes||size>cfg.dram_size_bytes-address)
                    throw std::runtime_error("tensor DMA outside original 2GiB partition");
                auto part=request;part.address=address;part.bytes=size;
                const auto begin=t;t=transfer(part,t);
                if(t<begin)throw std::runtime_error("DRAM callback precedes actual issue");
                log<<request.tile_id<<','<<request.is_write<<','<<address<<','<<size<<','<<begin<<','<<t<<'\n';
                bytes+=size;++segments;
            };
            if(request.is_write){
                if(!a.last||request.bytes!=a.mt*a.nt*cfg.output_bytes)throw std::runtime_error("bad native output tile");
                for(std::uint64_t row=0;row<a.mt;++row)
                    segment(output+((a.m+row)*N+a.n)*cfg.output_bytes,a.nt*cfg.output_bytes);
                write_bytes+=bytes;
            }else{
                for(std::uint64_t row=0;row<a.mt;++row)
                    segment(input+((a.m+row)*K+a.k)*cfg.activation_bytes,a.kt*cfg.activation_bytes);
                if(weight_stored_transposed){
                    for(std::uint64_t col=0;col<a.nt;++col)
                        segment(weight+((a.n+col)*K+a.k)*cfg.weight_bytes,a.kt*cfg.weight_bytes);
                }else{
                    // Attention S*V has a normal row-major [K,N] RHS, unlike
                    // model Linear weights, which are stored [N,K].
                    for(std::uint64_t row=0;row<a.kt;++row)
                        segment(weight+((a.k+row)*N+a.n)*cfg.weight_bytes,a.nt*cfg.weight_bytes);
                }
                read_bytes+=bytes;
            }
            if(bytes!=request.bytes)throw std::runtime_error("scatter DMA did not conserve native bytes");
            return t;
        };
        auto result=NPUSim::scheduleNpuTileEvents(plan,cfg,cycle,0,cb);
        cycle=std::max<unsigned long long>(cycle,result.overall_finish_cycle);
        std::cout<<"[NATIVE_LINEAR] "<<M<<' '<<K<<' '<<N<<' '<<plan.size()<<' '<<ops<<' '
            <<read_bytes<<' '<<write_bytes<<' '<<segments<<' '<<cycle<<std::endl;
        return result;
    }
};

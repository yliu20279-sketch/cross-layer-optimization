// Timing lowering for real-profile typed decoder vertices. Functional tensor
// equivalence is independently checked against actual model operands.
#include "native_linear.h"
#include "native_packed_linear.h"
#include "native_kernel.h"
#include "native_exchange.h"
#include "ring_local.h"
#include "line_receiver.h"
#include "sync_protocol.h"
#include <nlohmann/json.hpp>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>

using Json=nlohmann::json;
using Region=NativeKernel::Region;
static std::uint64_t product(const Json& shape){
    std::uint64_t n=1;for(const auto& x:shape)n*=x.get<std::uint64_t>();return n;
}
int main(int argc,char** argv){
    try{
        if(argc!=6)throw std::runtime_error("rank config topology plan stop_boundary required");
        const int rank=std::stoi(argv[1]);
        NativeCausalTrace::get().init(rank);
        const std::string boundary=argv[5];
        if(rank<0||rank>=16||boundary!="full_layer")
            throw std::runtime_error("only explicitly implemented complete decoder-block boundary may run");
        std::ifstream input(argv[4]);Json plan;input>>plan;
        if(plan.at("node")!=rank||plan.at("mapping")!="TP16+EP16/PP1")
            throw std::runtime_error("incorrect target node plan");
        auto cfg=NPUSim::loadConfig(argv[2]);cfg.topology_gv_path=argv[3];
        cfg.dram_chiplet_x=rank%4;cfg.dram_chiplet_y=4+rank/4;
        if(cfg.sram_per_mac_bytes!=4194304||cfg.dram_size_bytes!=2147483648ULL)
            throw std::runtime_error("target architecture capacities changed");
        const auto& tensors=plan.at("tensors");const auto& weights=plan.at("weights");
        const auto packing_base=std::to_string(plan.at("native_packing_scratch").at("base").get<std::uint64_t>());
        const auto packing_capacity=std::to_string(plan.at("native_packing_scratch").at("tensor_capacity").get<std::uint64_t>());
        setenv("NPU_PACKING_BASE",packing_base.c_str(),1);setenv("NPU_PACKING_CAPACITY",packing_capacity.c_str(),1);
        auto region=[&](const std::string& name)->Region{
            const auto& t=tensors.at(name);return {t.at("address"),t.at("bytes")};
        };
        std::filesystem::create_directories("reports");
        unsigned long long cycle=1;
        NPUSim::ChipletMemoryClientOptions options;options.self_x=rank%4;options.self_y=rank/4;
        options.transaction_trace_path="reports/dram_transactions.csv";
        NPUSim::ChipletMemoryClient memory(cfg,options,cycle);
        std::ofstream events("kernel_events.csv"),vertices("vertices.csv"),dma("native_tensor_dma.csv"),mac_events("native_mac_events.csv");
        mac_events<<"op,tile,mac,ops,read_issue,data_ready,mac_start,mac_finish,write_issue,write_complete,compute_cycles,local_memory_cycles\n";
        const char* record_mac=std::getenv("NPU_RECORD_MAC");
        std::ostream* mac_observer=record_mac&&std::string(record_mac)=="0"?nullptr:&mac_events;
        events<<"node,op,kind,address,bytes,ops,issue,start,finish\n";
        vertices<<"node,op,name,kind,start,finish\n";
        NativeKernel kernel(cfg,memory,rank,events);
        std::ofstream ring_events("local_events.csv");
        ring_events<<"node,label,event,kind,address,bytes,ops,issue,start,finish\n";
        NativeExchange exchange(cfg,memory,rank,ring_events);
        std::uint64_t executed=0;bool stopped=false;
        const bool nonblocking=InterChiplet::taggedNocRepliesEnabled();
        int active_batch=-1;
        auto batchKey=[&](const Json& op){
            const int phase=plan.at("per_operator_phase").at(std::to_string(op.at("id").get<std::uint64_t>()));
            if(phase!=2&&phase!=4)return -1;
            const std::string name=op.at("name");
            return std::stoi(name.substr(1,name.find('/')-1))*8+phase;
        };
        std::map<std::uint64_t,std::string> op_names;
        for(const auto& op:plan.at("operators"))op_names[op.at("id")]=op.at("name");
        auto finish_batch=[&](){
            for(const auto& v:exchange.finishBatch(cycle)){
                vertices<<rank<<','<<v.op<<','<<op_names.at(v.op)<<",transfer,"<<v.start<<','<<v.finish<<'\n';
                ++executed;
            }
            vertices.flush();active_batch=-1;
        };
        for(const auto& op:plan.at("operators")){
            const int key=nonblocking?batchKey(op):-1;
            if(active_batch!=-1&&key!=active_batch)finish_batch();
            if(key!=-1&&active_batch==-1){
                std::vector<NativeExchange::PostedReceive> receives;
                std::uint64_t workspace=0;
                for(const auto& candidate:plan.at("operators")){
                    if(batchKey(candidate)!=key)continue;
                    if(candidate.at("kind")=="transfer"&&candidate.at("source")!=rank&&candidate.at("destination")==rank){
                        const auto bytes=candidate.at("payload_bytes").get<std::uint64_t>();
                        const auto id=candidate.at("id").get<std::uint64_t>();
                        const int source=candidate.at("source");
                        const auto base=region(candidate.at("output")).first;
                        for(std::uint64_t offset=0;offset<bytes;offset+=32768)
                            receives.push_back({id,NativeExchange::transferTag(id,offset/32768,source,rank),
                                source,std::min<std::uint64_t>(32768,bytes-offset),base+offset});
                    }else if(candidate.at("rank")==rank){
                        std::set<Region> inputs;
                        for(const auto& name:candidate.at("inputs"))if(tensors.contains(name.get<std::string>()))
                            inputs.insert(region(name));
                        std::uint64_t footprint=0;
                        for(const auto& r:inputs)footprint+=(r.second+31)/32*32;
                        footprint+=(region(candidate.at("output")).second+31)/32*32;
                        workspace=std::max(workspace,footprint);
                    }
                }
                exchange.beginBatch(cycle,receives,workspace);active_batch=key;
            }
            if(op.at("kind")=="transfer"&&op.at("source")==rank&&op.at("destination")!=rank){
                const auto start=cycle;
                exchange.transfer(cycle,op.at("id"),rank,op.at("destination"),op.at("payload_bytes"),
                    region(op.at("inputs").at(0)).first);
                vertices<<rank<<','<<op.at("id")<<','<<op.at("name").get<std::string>()
                    <<",transfer_send,"<<start<<','<<cycle<<'\n';vertices.flush();
            }
            if(op.at("rank")!=rank)continue;
            if(active_batch!=-1&&op.at("kind")=="transfer"&&op.at("source")!=rank)continue;
            const auto id=op.at("id").get<std::uint64_t>();
            const auto kind=op.at("kind").get<std::string>();
            const auto name=op.at("name").get<std::string>();
            const auto out=region(op.at("output"));const auto start=cycle;
            std::vector<Region> ins;for(const auto& i:op.at("inputs"))
                if(tensors.contains(i.get<std::string>()))ins.push_back(region(i));
            std::vector<std::uint64_t> input_rows;
            for(const auto& i:op.at("inputs"))if(tensors.contains(i.get<std::string>())){
                const auto& s=tensors.at(i.get<std::string>()).at("shape");
                input_rows.push_back(product(s)/s.at(s.size()-1).get<std::uint64_t>());
            }
            const auto& shape=tensors.at(op.at("output").get<std::string>()).at("shape");
            const auto elements=product(shape);
            if(kind=="linear"){
                const auto& x=tensors.at(op.at("inputs").at(0).get<std::string>());
                const auto& w=weights.at(op.at("weight").get<std::string>());
                if(w.at("layout")!="packed_NK_64")throw std::runtime_error("static weight was not compiled in native packed order");
                NativePackedLinear::run(cfg,memory,cycle,x.at("shape").at(0),x.at("shape").at(1),
                    w.at("shape").at(0),x.at("address"),w.at("address"),out.first,dma,true,true,mac_observer,id);
                if(!op.at("bias").is_null()){
                    const auto& bias=weights.at(op.at("bias").get<std::string>());
                    kernel.run(cycle,id,{out,{bias.at("address"),bias.at("bytes")}},{out},elements,0);
                }
            }else if(kind=="batched_matmul_transpose_right"||kind=="batched_matmul"){
                const auto& left=tensors.at(op.at("inputs").at(0).get<std::string>());
                const auto& right=tensors.at(op.at("inputs").at(1).get<std::string>());
                const auto& ls=left.at("shape");const auto& rs=right.at("shape");
                const auto M=ls.at(ls.size()-2).get<std::uint64_t>();
                const auto K=ls.at(ls.size()-1).get<std::uint64_t>();
                const bool transposed=kind=="batched_matmul_transpose_right";
                const auto N=rs.at(rs.size()-(transposed?2:1)).get<std::uint64_t>();
                const auto batches=product(ls)/(M*K);
                if(product(rs)!=batches*K*N||product(shape)!=batches*M*N)
                    throw std::runtime_error("attention batch dimension contract failed");
                for(std::uint64_t b=0;b<batches;++b)
                    NativePackedLinear::run(cfg,memory,cycle,M,K,N,
                        left.at("address").get<std::uint64_t>()+b*M*K*2,
                        right.at("address").get<std::uint64_t>()+b*K*N*2,out.first+b*M*N*2,dma,transposed,false,mac_observer,id);
            }else if(kind=="all_reduce"||kind=="reduce_scatter"||kind=="all_gather"){
                if(ins.size()!=1)throw std::runtime_error("collective must consume exactly one locally owned tensor");
                exchange.ring(cycle,id,op.at("collective_id"),kind,ins.at(0),out);
            }else if(kind=="transfer"){
                if(op.at("source")==rank)kernel.run(cycle,id,ins,{out},0,0);
                else exchange.transfer(cycle,id,op.at("source"),rank,op.at("payload_bytes"),out.first);
            }else{
                std::uint64_t v=0,r=0;
                if(kind=="cast"||kind=="mul"||kind=="broadcast_mul"||kind=="scale"||
                    kind=="add_causal_mask"||kind=="broadcast_sub"||kind=="exp"||kind=="broadcast_div"||
                    kind=="add"||kind=="silu"||kind=="sigmoid")v=elements;
                else if(kind=="reduce_mean"||kind=="reduce_sum"||kind=="reduce_max"){
                    r=product(tensors.at(op.at("inputs").at(0).get<std::string>()).at("shape"));
                    if(kind=="reduce_mean")v=elements;
                }else if(kind=="add_epsilon_rsqrt")v=2*elements;
                else if(kind=="rotary_position_embedding")v=3*elements+elements/2;
                else if(kind=="softmax_fp32"){
                    // Explicit stable softmax: max, subtract, exp, sum, divide.
                    const auto n=product(tensors.at(op.at("inputs").at(0).get<std::string>()).at("shape"));
                    r=2*n;v=3*n;
                }else if(kind=="topk"){
                    // Four repeated maximum/index reductions over 60 experts;
                    // this is an explicit primitive implementation, not a
                    // timing guessed from a GPU kernel.
                    const auto n=product(tensors.at(op.at("inputs").at(0).get<std::string>()).at("shape"));
                    const auto k=op.at("k").get<std::uint64_t>();r=k*n;v=k*n;
                    if(op.at("renormalize").get<bool>()){r+=elements;v+=elements;}
                }else if(kind=="weighted_scatter_add"){
                    // Every selected expert value is multiplied once and added
                    // once. Gate weights/indices are metadata, not activations.
                    std::uint64_t values=0;
                    for(std::size_t i=0;i+2<op.at("inputs").size();++i)
                        values+=product(tensors.at(op.at("inputs").at(i).get<std::string>()).at("shape"));
                    v=2*values;
                }
                else if(kind=="weight_mul"){
                    const auto& w=weights.at(op.at("weight").get<std::string>());
                    ins.push_back({w.at("address"),w.at("bytes")});input_rows.push_back(1);v=elements;
                }else if(kind!="kv_cache_write"&&kind!="transpose_contiguous"&&kind!="strided_gather_tokens"&&
                    kind!="pack_expert_tokens"&&kind!="concat"&&kind!="slice_rows")
                    throw std::runtime_error("unimplemented operator must not be silently skipped: "+name+"/"+kind);
                std::vector<Region> outs{out};for(const auto& secondary:op.value("secondary_outputs",Json::array()))
                    outs.push_back(region(secondary));
                if(kind=="strided_gather_tokens"||kind=="pack_expert_tokens"){
                    const auto& source=tensors.at(op.at("inputs").at(0).get<std::string>());
                    const auto base=source.at("address").get<std::uint64_t>();
                    const auto width=source.at("shape").at(1).get<std::uint64_t>()*2;
                    std::vector<Region> selected;
                    if(kind=="strided_gather_tokens"){
                        for(const auto& index:op.at("indices"))selected.push_back({base+index.get<std::uint64_t>()*width,width});
                    }else{
                        for(const auto& item:op.at("token_map")){
                            const auto token=item.at("flat_token").get<std::uint64_t>();
                            if(token%16!=std::uint64_t(rank))throw std::runtime_error("expert pack token owner mismatch");
                            selected.push_back({base+(token/16)*width,width});
                        }
                        for(std::size_t i=1;i<ins.size();++i)selected.push_back(ins[i]);
                    }
                    kernel.run(cycle,id,selected,outs,v,r);
                }else if(kind=="slice_rows"){
                    const auto& source=tensors.at(op.at("inputs").at(0).get<std::string>());
                    const auto width=source.at("shape").at(1).get<std::uint64_t>()*2;
                    kernel.run(cycle,id,{{ins.at(0).first+op.at("begin").get<std::uint64_t>()*width,out.second}},outs,v,r);
                }else if(kind=="concat"||kind=="weighted_scatter_add")kernel.run(cycle,id,ins,outs,v,r);
                else kernel.runRows(cycle,id,ins,outs,v,r,elements/shape.at(shape.size()-1).get<std::uint64_t>(),input_rows);
            }
            vertices<<rank<<','<<id<<','<<name<<','<<kind<<','<<start<<','<<cycle<<'\n';vertices.flush();
            ++executed;
        }
        if(active_batch!=-1)finish_batch();
        stopped=executed>0;
        if(!stopped)throw std::runtime_error("empty decoder program");
        memory.shutdown();
        std::cout<<"[DECODER_PREFIX] "<<rank<<' '<<executed<<' '<<cycle<<' '
            <<memory.completionRecords().size()<<std::endl;
        InterChiplet::sendCycleCmd(cycle);
    }catch(const std::exception& e){std::cerr<<e.what()<<std::endl;return 1;}
}

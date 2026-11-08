#pragma once
#include <fstream>
#include <cstdlib>
#include <cstdint>
#include <stdexcept>
#include <string>
// Read-only trace of actual native program waits and actual SRAM callbacks.
// These records guide a numerical waveform iteration, not modeled hardware.
class NativeCausalTrace {
    bool enabled_=false,initialized_=false;
    int node_=-1;
    std::uint64_t fence_=0,base_=0;
    std::ofstream out_,memory_out_;
    bool memory_enabled_=false;
    std::uint64_t memory_fence_=0,memory_base_=0;
    NativeCausalTrace()=default;
public:
    static NativeCausalTrace&get(){static NativeCausalTrace t;return t;}
    void init(int node){
        if(initialized_)throw std::runtime_error("causal trace initialized twice");
        initialized_=true;node_=node;const char*p=std::getenv("NPU_CAUSAL_TRACE");enabled_=p&&std::string(p)=="1";
        if(enabled_){out_.open("causal_program.txt");if(!out_)throw std::runtime_error("cannot open native program trace");}
        const char*d=std::getenv("NPU_CAUSAL_DDR_TRACE");memory_enabled_=d&&std::string(d)=="1";
        if(memory_enabled_){
            if(!enabled_)throw std::runtime_error("DDR causal trace requires native causal trace");
            memory_out_.open("causal_memory_program.txt");
            if(!memory_out_)throw std::runtime_error("cannot open native DDR program trace");
        }
    }
    void service(std::uint64_t time,std::uint64_t bytes){
        if(!enabled_)return;
        if(!initialized_||time<=base_||!bytes||bytes>256)throw std::runtime_error("native service outside causal context");
        out_<<"service "<<node_<<' '<<fence_<<' '<<time-base_<<' '<<bytes<<' '<<time<<'\n';
        if(memory_enabled_){
            if(time<=memory_base_)throw std::runtime_error("SRAM service not after actual DDR/NoC completion");
            memory_out_<<"service "<<node_<<' '<<memory_fence_<<' '<<time-memory_base_<<' '<<bytes<<' '<<time<<'\n';
        }
    }
    void release(std::uint64_t desc,bool send,std::uint64_t time){
        if(!enabled_)return;
        if(time<base_)throw std::runtime_error("native command before last blocking wait");
        out_<<"release "<<node_<<' '<<fence_<<' '<<desc<<' '<<send<<' '<<time-base_<<'\n';out_.flush();
        if(memory_enabled_){
            if(time<memory_base_)throw std::runtime_error("command before actual DDR completion");
            memory_out_<<"release "<<node_<<' '<<memory_fence_<<' '<<desc<<' '<<send<<' '<<time-memory_base_<<'\n';
        }
    }
    void wait(std::uint64_t before,std::uint64_t after,std::uint64_t tx,std::uint64_t rx){
        if(!enabled_)return;
        if(before<base_||after<before||(!tx&&!rx))throw std::runtime_error("invalid actual blocking wait");
        const auto parent=fence_++;
        out_<<"fence "<<node_<<' '<<fence_<<' '<<parent<<' '<<before-base_<<' '<<tx<<' '<<rx<<' '<<after<<'\n';
        base_=after;out_.flush();
        if(memory_enabled_){
            if(before<memory_base_)throw std::runtime_error("wait before actual DDR completion");
            const auto mp=memory_fence_++;
            memory_out_<<"fence "<<node_<<' '<<memory_fence_<<' '<<mp<<' '<<before-memory_base_<<' '<<tx<<' '<<rx<<' '<<after<<'\n';
            memory_base_=after;memory_out_.flush();
        }
    }
    void dram(std::uint64_t before,std::uint64_t after,bool write,std::uint64_t address,std::uint64_t bytes,std::uint64_t id){
        if(!memory_enabled_)return;
        if(!initialized_||before<memory_base_||after<=before||!bytes||!id)
            throw std::runtime_error("invalid observed blocking DRAM completion");
        const auto parent=memory_fence_++;
        memory_out_<<"dram "<<node_<<' '<<memory_fence_<<' '<<parent<<' '<<before-memory_base_
            <<' '<<write<<' '<<address<<' '<<bytes<<' '<<id<<' '<<after<<'\n';
        memory_base_=after;
    }
};

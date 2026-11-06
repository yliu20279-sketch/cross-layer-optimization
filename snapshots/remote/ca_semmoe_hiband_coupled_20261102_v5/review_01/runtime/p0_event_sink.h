#pragma once
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <map>
#include <stdexcept>
#include <string>
#include <tuple>
#include <cctype>
#include <cmath>
#include <set>

namespace p0 {
inline void check(bool ok, const char* message) { if (!ok) throw std::runtime_error(message); }
struct Object { int partition; uint64_t address, bytes, generation; bool movable; };
struct Pending { int request; uint64_t offset, bytes; double accepted; };
using Key = std::tuple<int, uint64_t, uint64_t, uint64_t>;

// Hooked after successful backend admission, and at the actual callback.
// Does not invent a DRAM service time, change scheduling, or read packed data.
class EventSink {
    std::map<uint64_t,Object> objects_;
    std::map<int,std::string> requests_;
    std::map<Key,Pending> pending_;
    std::set<Key> seen_;
    std::ofstream stream_;
    std::string split_;
    void write(const char* event,int request,int rank,uint64_t object,uint64_t op,
               uint64_t token,uint64_t offset,uint64_t bytes,double time) {
        const auto& obj=objects_.at(object);
        stream_ << "{\"event\":\"" << event << "\",\"split\":\"" << split_ << "\",\"time\":" << time
          << ",\"request_id\":\"" << requests_.at(request) << "\",\"owner\":" << request
          << ",\"partition\":" << rank << ",\"object_id\":\"object_" << object
          << "\",\"generation\":" << obj.generation << ",\"op_id\":" << op
          << ",\"transaction_id\":" << token << ",\"offset\":" << offset
          << ",\"bytes\":" << bytes << ",\"object_bytes\":" << obj.bytes
          << ",\"role\":\"weight\",\"router\":false}\n";
    }
public:
    EventSink(const std::string& output,const std::string& objects,const std::string& requests,
              const std::string& dtype,const std::string& split):split_(split) {
        check(dtype=="F16","this adapter is FP16 only; no BF16 relabeling");
        check(split=="profile"||split=="eval","explicit profile/eval trace class required");
        {std::ifstream existing(output);check(!existing.good(),"refuse overwrite event output");}
        stream_.open(output);
        std::ifstream input(objects); uint64_t count=0; input >> count;
        check(bool(input)&&count>0,"object sidecar missing");
        for(uint64_t i=0;i<count;++i) {
            uint64_t id;Object object;int movable;
            input >> id >> object.partition >> object.address >> object.bytes >> object.generation >> movable;
            check(bool(input)&&object.bytes>0&&(movable==0||movable==1),"bad object sidecar");
            object.movable=movable;check(objects_.emplace(id,object).second,"duplicate object");
        }
        std::ifstream req(requests);req >> count;check(bool(req)&&count>0,"request sidecar missing");
        for(uint64_t i=0;i<count;++i) {
            int id;std::string name;req >> id >> name;
            check(bool(req)&&id>=0&&!name.empty(),"bad request identity");
            for(unsigned char c:name)check(std::isalnum(c)||c=='_'||c=='-'||c=='.'||c==':',"unsafe request ID");
            check(requests_.emplace(id,name).second,"duplicate request");
        }
        check(bool(stream_),"event output unavailable");stream_ << std::setprecision(17);
    }
    void accept(int request,int rank,uint64_t object,uint64_t op,uint64_t token,
                uint64_t logical,uint64_t bytes,bool write_request,double time) {
        check(objects_.count(object),"unknown operand object");const auto& obj=objects_.at(object);
        if(write_request||!obj.movable)return;
        check(requests_.count(request)&&rank==obj.partition,"operand/request identity mismatch");
        check(std::isfinite(time)&&time>=0&&logical>=obj.address&&bytes>0&&logical-obj.address<=obj.bytes
              &&bytes<=obj.bytes-(logical-obj.address),"operand extent invalid");
        uint64_t offset=logical-obj.address;Key key{rank,object,op,token};
        check(seen_.emplace(key).second,"reused accepted transaction identity");
        check(pending_.emplace(key,Pending{request,offset,bytes,time}).second,"duplicate accepted transaction");
        write("accept",request,rank,object,op,token,offset,bytes,time);
    }
    void callback(int rank,uint64_t object,uint64_t op,uint64_t token,bool write_request,double time) {
        check(objects_.count(object),"unknown callback object");const auto& obj=objects_.at(object);
        if(write_request||!obj.movable)return;
        Key key{rank,object,op,token};auto found=pending_.find(key);
        check(found!=pending_.end(),"unpaired/duplicate callback");const auto pending=found->second;
        check(std::isfinite(time)&&time>=pending.accepted,"callback before accepted");
        write("callback",pending.request,rank,object,op,token,pending.offset,pending.bytes,time);
        pending_.erase(found);
    }
    void finish() {check(pending_.empty(),"unclosed profile transaction");stream_.flush();check(bool(stream_),"event flush failed");}
};
}

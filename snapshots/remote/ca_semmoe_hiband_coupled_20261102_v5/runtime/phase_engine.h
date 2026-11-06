#pragma once
#include <cstdint>
#include <vector>
#include <unordered_map>
#include <stdexcept>
#include <algorithm>
#include <limits>
namespace realv2 {
enum class Phase {Ready,Read,ComputeReady,Compute,Write,Done};
struct Segment {uint64_t address,bytes;uint32_t object;bool write;};
struct Transaction {uint32_t owner,object;uint64_t token,address,bytes;bool write;};
class Operation {
 uint32_t owner_;size_t limit_;std::vector<Transaction> reads_,writes_;size_t cursor_=0;uint64_t serial_=0,service_=0;double finish_=0;std::unordered_map<uint64_t,Transaction> live_;
 void require(bool value,const char*message)const {if(!value)throw std::runtime_error(message);}
 std::vector<Transaction>&stream(){return phase==Phase::Read?reads_:writes_;}
 void advance(){if((phase==Phase::Read||phase==Phase::Write)&&cursor_==stream().size()&&live_.empty()){if(phase==Phase::Read)phase=Phase::ComputeReady;else phase=Phase::Done;cursor_=0;}}
public:
 Phase phase=Phase::Ready;size_t peak=0;uint64_t issued=0,completed=0;
 Operation(uint32_t owner,size_t limit,const std::vector<Segment>&segments,uint64_t compute_cycles):owner_(owner),limit_(limit),service_(compute_cycles){
  require(limit>0,"zero original-op credit");
  for(auto&s:segments){require(s.bytes>0&&s.address<=std::numeric_limits<uint64_t>::max()-s.bytes,"invalid segment");uint64_t off=0;
   while(off<s.bytes){uint64_t address=s.address+off;uint64_t chunk=std::min({uint64_t(256),s.bytes-off,4096-address%4096});Transaction t{owner,s.object,serial_++,address,chunk,s.write};(s.write?writes_:reads_).push_back(t);off+=chunk;}}
 }
 void release(){require(phase==Phase::Ready,"duplicate release");phase=Phase::Read;advance();}
 bool pending() {return (phase==Phase::Read||phase==Phase::Write)&&cursor_<stream().size()&&live_.size()<limit_;}
 Transaction peek(){require(pending(),"no issuable transaction");return stream()[cursor_];}
 // Backend rejection must not call accept: cursor, token and credit remain unchanged.
 void accept(const Transaction&t){auto expected=peek();require(t.owner==owner_&&t.token==expected.token&&t.address==expected.address&&t.bytes==expected.bytes&&t.object==expected.object&&t.write==expected.write,"invalid transaction admission");require(live_.emplace(t.token,t).second,"duplicate admission");++cursor_;++issued;peak=std::max(peak,live_.size());}
 void callback(uint32_t owner,uint64_t token){require(owner==owner_,"wrong owner callback");auto it=live_.find(token);require(it!=live_.end(),"unknown or duplicate callback");live_.erase(it);++completed;advance();}
 void admit_compute(double now){require(phase==Phase::ComputeReady,"compute before reads complete");finish_=now+service_;phase=Phase::Compute;}
 void compute_complete(double now){require(phase==Phase::Compute&&now>=finish_,"early or duplicate compute completion");phase=Phase::Write;cursor_=0;advance();}
 bool consumer_ready()const{return phase==Phase::Done;}
 size_t outstanding()const{return live_.size();}
};
}

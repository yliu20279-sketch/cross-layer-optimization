#pragma once
#include <cstdint>
#include <vector>
#include <unordered_map>
#include <stdexcept>
#include <algorithm>
#include <limits>
namespace tiledfp16 {
inline void require(bool ok,const char*m){if(!ok)throw std::runtime_error(m);}
class Sram {
 uint64_t capacity_,used_=0;std::unordered_map<uint32_t,uint64_t> leases_;
public:
 uint64_t peak=0;
 explicit Sram(uint64_t cap):capacity_(cap){require(cap>0,"zero SRAM");}
 bool reserve(uint32_t owner,uint64_t bytes){require(!leases_.count(owner),"duplicate SRAM owner");require(bytes>0&&bytes<=capacity_,"impossible SRAM request");if(bytes>capacity_-used_)return false;leases_[owner]=bytes;used_+=bytes;peak=std::max(peak,used_);return true;}
 void release(uint32_t owner){auto i=leases_.find(owner);require(i!=leases_.end(),"unknown SRAM lease");used_-=i->second;leases_.erase(i);}
 uint64_t used()const{return used_;}
};
enum class Phase {Ready,Read,ComputeReady,Compute,Write,Done};
struct Tx {uint32_t owner,object;uint64_t token,address,bytes;bool write;};
// A[M,K], B[K,N] FP16 row-major; C[M,N] FP16. Accumulator FP32.
// Tile traversal m,n,k; accumulator retained over increasing k and cast only at final k.
class Operation {
 Sram&pool_;uint32_t owner_;size_t limit_;uint64_t M_,K_,N_,a_,b_,c_;uint32_t ao_,bo_,co_;uint64_t mt_=0,nt_=0,kt_=0,next_=0;bool leased_=false;size_t cursor_=0;std::vector<Tx>stream_;std::unordered_map<uint64_t,Tx>live_;double finish_=0;
 uint64_t mm()const{return std::min(uint64_t(64),M_-mt_);}uint64_t nn()const{return std::min(uint64_t(64),N_-nt_);}uint64_t kk()const{return std::min(uint64_t(64),K_-kt_);}
 void segment(uint32_t object,uint64_t address,uint64_t bytes,bool write){require(address<=std::numeric_limits<uint64_t>::max()-bytes,"segment overflow");while(bytes){auto n=std::min({uint64_t(256),bytes,4096-address%4096});stream_.push_back({owner_,object,next_++,address,n,write});address+=n;bytes-=n;}}
 void read_tile(){stream_.clear();cursor_=0;for(uint64_t i=0;i<mm();++i)segment(ao_,a_+2*((mt_+i)*K_+kt_),2*kk(),false);for(uint64_t k=0;k<kk();++k)segment(bo_,b_+2*((kt_+k)*N_+nt_),2*nn(),false);phase=Phase::Read;}
 void next_output(){require(live_.empty()&&leased_,"unsafe SRAM release");pool_.release(owner_);leased_=false;kt_=0;nt_+=64;if(nt_>=N_){nt_=0;mt_+=64;}phase=mt_>=M_?Phase::Done:Phase::Ready;}
 void advance(){if(cursor_==stream_.size()&&live_.empty()){if(phase==Phase::Read)phase=Phase::ComputeReady;else if(phase==Phase::Write)next_output();}}
public:
 Phase phase=Phase::Ready;uint64_t issued=0,completed=0,tiles=0,read_bytes=0,write_bytes=0;size_t peak_credit=0;
 Operation(Sram&pool,uint32_t owner,size_t credit,uint64_t M,uint64_t K,uint64_t N,uint64_t A,uint64_t B,uint64_t C,uint32_t ao,uint32_t bo,uint32_t co):pool_(pool),owner_(owner),limit_(credit),M_(M),K_(K),N_(N),a_(A),b_(B),c_(C),ao_(ao),bo_(bo),co_(co){
  require(M&&K&&N&&credit,"invalid shape/credit");auto max=std::numeric_limits<uint64_t>::max();require(M<=max/K/2&&K<=max/N/2&&M<=max/N/2,"tensor size overflow");require(A<=max-M*K*2&&B<=max-K*N*2&&C<=max-M*N*2,"tensor address overflow");
 }
 uint64_t reservation_bytes()const{require(phase==Phase::Ready,"reservation outside ready");auto m=mm(),n=nn(),k=std::min(uint64_t(64),K_);return 2*m*k+2*k*n+4*m*n+2*m*n;}
 bool try_start(){require(phase==Phase::Ready,"start outside ready");auto bytes=reservation_bytes();if(!pool_.reserve(owner_,bytes))return false;leased_=true;read_tile();return true;}
 bool pending()const{return (phase==Phase::Read||phase==Phase::Write)&&cursor_<stream_.size()&&live_.size()<limit_;}
 Tx peek()const{require(pending(),"nothing issuable");return stream_[cursor_];}
 void accept(const Tx&t){auto e=peek();require(t.owner==owner_&&t.token==e.token&&t.object==e.object&&t.address==e.address&&t.bytes==e.bytes&&t.write==e.write,"wrong admission");require(live_.emplace(t.token,t).second,"duplicate token");++cursor_;++issued;peak_credit=std::max(peak_credit,live_.size());(t.write?write_bytes:read_bytes)+=t.bytes;}
 void callback(uint32_t owner,uint64_t token){require(owner==owner_,"wrong owner");require(live_.erase(token)==1,"unknown/duplicate callback");++completed;advance();}
 void admit_compute(double now,uint64_t cycles){require(phase==Phase::ComputeReady,"compute before reads");finish_=now+cycles;phase=Phase::Compute;}
 void compute_complete(double now){require(phase==Phase::Compute&&now>=finish_,"early compute completion");++tiles;kt_+=64;if(kt_<K_){read_tile();return;}stream_.clear();cursor_=0;for(uint64_t i=0;i<mm();++i)segment(co_,c_+2*((mt_+i)*N_+nt_),2*nn(),true);phase=Phase::Write;advance();}
 bool consumer_ready()const{return phase==Phase::Done;}
 size_t outstanding()const{return live_.size();}
 uint64_t m_offset()const{return mt_;}uint64_t n_offset()const{return nt_;}uint64_t k_offset()const{return kt_;}
};
}

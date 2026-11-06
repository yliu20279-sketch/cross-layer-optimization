#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <map>
#include <set>
#include <stdexcept>
#include <tuple>
#include <vector>

namespace p0live {
inline void need(bool x,const char* why) { if(!x) throw std::runtime_error(why); }
using Page = std::pair<int,uint64_t>;
struct PageInfo { uint64_t physical; bool movable; };
// All registered pages, including fixed workspace, share the same finite
// partition frame pool. This is applied before actual Ramulator admission.
class AddressMap {
    std::map<Page,PageInfo> base_;
    std::map<Page,uint64_t> current_;
    std::set<Page> occupied_;
    std::map<uint64_t,Page> live_;
    std::set<uint64_t> seen_;
    std::vector<uint64_t> capacities_;
    uint64_t generation_=0;
public:
    explicit AddressMap(std::vector<uint64_t> caps):capacities_(std::move(caps)) {
        need(!capacities_.empty(),"empty capacities");
        for(auto c:capacities_) need(c&&c%4096==0,"invalid partition extent");
    }
    void add(int partition,uint64_t logical,uint64_t physical,bool movable) {
        need(live_.empty()&&generation_==0,"late registration");
        need(partition>=0&&size_t(partition)<capacities_.size(),"unknown partition");
        need(physical<capacities_[partition]/4096,"physical frame outside partition");
        need(!occupied_.count({partition,physical}),"base physical alias");
        need(base_.emplace(Page{partition,logical},PageInfo{physical,movable}).second,"duplicate logical page");
        occupied_.insert({partition,physical});
        current_[{partition,logical}]=physical;
    }
    void install(const std::map<Page,uint64_t>& candidate,uint64_t expected_generation) {
        need(live_.empty(),"map install before drain");
        need(expected_generation==generation_,"stale map installation");
        need(!candidate.empty()&&candidate.size()==base_.size(),"page domain changed");
        std::map<int,std::set<uint64_t>> old_pool,new_pool;
        for(auto& row:base_) {
            auto it=candidate.find(row.first); need(it!=candidate.end(),"page missing");
            need(it->second<capacities_[row.first.first]/4096,"map frame outside capacity");
            need(row.second.movable||it->second==row.second.physical,"fixed page moved");
            old_pool[row.first.first].insert(row.second.physical);
            need(new_pool[row.first.first].insert(it->second).second,"candidate physical alias");
        }
        need(old_pool==new_pool,"partition frame pool changed");
        current_=candidate; ++generation_;
    }
    uint64_t translate(int partition,uint64_t logical,uint64_t bytes,uint64_t generation) const {
        need(generation==generation_,"stale address generation");
        need(bytes&&bytes<=4096&&logical%4096<=4096-bytes,"unsplit cross-page transaction");
        auto it=current_.find({partition,logical/4096});need(it!=current_.end(),"unregistered logical page");
        return it->second*4096+logical%4096;
    }
    void accept(uint64_t transaction,int partition,uint64_t logical,uint64_t bytes,uint64_t generation) {
        translate(partition,logical,bytes,generation);
        need(seen_.insert(transaction).second,"reused transaction ID");
        need(live_.emplace(transaction,Page{partition,logical/4096}).second,"duplicate admission");
    }
    void callback(uint64_t transaction,uint64_t generation) {
        need(generation==generation_,"callback generation changed");
        need(live_.erase(transaction)==1,"unknown/duplicate map callback");
    }
    size_t inflight() const { return live_.size(); }
    uint64_t generation() const { return generation_; }
};

// Project HiBand-inspired injection-budget model, not author HIC/split-Benes.
// Budget is bytes per explicit interval; packet occupancy uses actual flit
// size, including padding. In-flight packets prevent mode switching.
class LinkController {
    uint64_t local_budget_=512,global_budget_=1024,interval_,switch_,next_id_=0;
    uint64_t used_local_=0,used_global_=0,epoch_=0;
    double ready_=0,last_=0;
    std::map<uint64_t,std::pair<bool,uint64_t>> live_;
    bool local_bias_=false;
    void advance(double now) {
        need(std::isfinite(now)&&now>=last_,"nonmonotonic control clock");last_=now;
        auto e=uint64_t(std::floor(now/double(interval_)));
        if(e!=epoch_) { epoch_=e;used_local_=used_global_=0; }
    }
public:
    uint64_t switches=0,accepted_bytes=0;
    LinkController(uint64_t interval,uint64_t switching):interval_(interval),switch_(switching) {
        need(interval>0,"zero bandwidth interval");
    }
    bool select(uint64_t local_pending,uint64_t global_pending,double now) {
        advance(now); bool desired=local_pending>global_pending;
        if(desired==local_bias_||!live_.empty()||now<ready_)return false;
        local_bias_=desired; local_budget_=desired?1024:512;global_budget_=1536-local_budget_;
        ready_=now+switch_;++switches;return true;
    }
    bool can_issue(bool local,uint64_t bytes,double now) {
        advance(now);need(bytes>0,"empty packet");
        auto budget=local?local_budget_:global_budget_;auto used=local?used_local_:used_global_;
        need(bytes<=512,"packet exceeds minimum supported domain budget");
        return now>=ready_&&used<=budget&&bytes<=budget-used;
    }
    uint64_t accept(bool local,uint64_t bytes,double now) {
        need(can_issue(local,bytes,now),"packet accepted without budget");
        (local?used_local_:used_global_)+=bytes;
        auto id=next_id_++;live_[id]={local,bytes};accepted_bytes+=bytes;return id;
    }
    void callback(uint64_t id,double now) {
        advance(now);need(live_.erase(id)==1,"unknown/duplicate packet callback");
    }
    uint64_t local_budget()const{return local_budget_;}
    uint64_t global_budget()const{return global_budget_;}
    size_t inflight()const{return live_.size();}
    double ready()const{return ready_;}
};
}

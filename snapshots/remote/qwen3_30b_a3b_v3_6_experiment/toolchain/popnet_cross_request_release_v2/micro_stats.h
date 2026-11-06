#ifndef POPNET_MICRO_STATS_H
#define POPNET_MICRO_STATS_H

#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <map>
#include <string>
#include <tuple>

class PopnetMicroStats {
public:
    struct VCWindow {
        double occupancy_cycle_sum = 0.0;
        double active_cycle_sum = 0.0;
        long max_occupancy = 0;
        unsigned long long queue_writes = 0;
        unsigned long long queue_reads = 0;
        unsigned long long vc_requests = 0;
        unsigned long long vc_grants = 0;
        unsigned long long vc_blocked_unavailable = 0;
        unsigned long long sw_requests = 0;
        unsigned long long sw_grants = 0;
        unsigned long long sw_blocked_no_credit = 0;
        unsigned long long sw_blocked_outbuffer = 0;
    };
    struct RouterWindow {
        unsigned long long crossbar_flits = 0;
        unsigned long long link_flits = 0;
    };
    struct QueueState {
        double last_time = 0.0;
        long occupancy = 0;
        bool initialized = false;
    };

private:
    typedef std::tuple<long,long,long> VCKey;
    typedef std::tuple<long,long,long,long> VCWindowKey;
    typedef std::pair<long,long> RouterWindowKey;
    std::map<VCKey,QueueState> queue_state_;
    std::map<VCWindowKey,VCWindow> vc_windows_;
    std::map<RouterWindowKey,RouterWindow> router_windows_;
    double window_cycles_;
    std::string output_dir_;
    bool enabled_;

    PopnetMicroStats() : window_cycles_(2500000.0), output_dir_("."), enabled_(false) {
        const char *dir = std::getenv("POPNET_STATS_DIR");
        if (dir && *dir) { output_dir_ = dir; enabled_ = true; }
        const char *window = std::getenv("POPNET_STATS_WINDOW_CYCLES");
        if (window && *window) {
            double parsed = std::atof(window);
            if (parsed > 0.0) window_cycles_ = parsed;
        }
    }
    long window_id(double time) const { return static_cast<long>(time / window_cycles_); }
    void integrate(const VCKey &key, QueueState &state, double end_time) {
        if (!state.initialized || end_time <= state.last_time) return;
        double cursor = state.last_time;
        const long router = std::get<0>(key), port = std::get<1>(key), vc = std::get<2>(key);
        while (cursor < end_time) {
            long w = window_id(cursor);
            double stop = std::min(end_time, (w + 1) * window_cycles_);
            VCWindow &out = vc_windows_[VCWindowKey(router,port,vc,w)];
            out.occupancy_cycle_sum += state.occupancy * (stop - cursor);
            if (state.occupancy > 0) out.active_cycle_sum += stop - cursor;
            out.max_occupancy = std::max(out.max_occupancy, state.occupancy);
            cursor = stop;
        }
    }
    VCWindow &vcw(long router,long port,long vc,double time) {
        return vc_windows_[VCWindowKey(router,port,vc,window_id(time))];
    }
    RouterWindow &rw(long router,double time) {
        return router_windows_[RouterWindowKey(router,window_id(time))];
    }

public:
    static PopnetMicroStats &instance() { static PopnetMicroStats recorder; return recorder; }
    std::pair<double,double> coupled_counts(long router,long window) const {
        auto i=router_windows_.find(RouterWindowKey(router,window));
        if(i==router_windows_.end())return {0.,0.};
        return {double(i->second.crossbar_flits),double(i->second.link_flits)};
    }
    bool enabled() const { return enabled_; }
    void queue_change(long router,long port,long vc,long new_occupancy,double time,bool write,bool read) {
        if (!enabled_) return;
        VCKey key(router,port,vc); QueueState &state = queue_state_[key];
        if (!state.initialized) { state.initialized=true; state.last_time=time; state.occupancy=0; }
        integrate(key,state,time); state.last_time=time; state.occupancy=new_occupancy;
        VCWindow &out=vcw(router,port,vc,time); out.max_occupancy=std::max(out.max_occupancy,new_occupancy);
        if (write) ++out.queue_writes; if (read) ++out.queue_reads;
    }
    void vc_request(long r,long p,long v,double t,bool unavailable) {
        if (!enabled_) return; VCWindow &x=vcw(r,p,v,t); ++x.vc_requests; if(unavailable) ++x.vc_blocked_unavailable;
    }
    void vc_grant(long r,long p,long v,double t) { if(enabled_) ++vcw(r,p,v,t).vc_grants; }
    void sw_request(long r,long p,long v,double t,bool no_credit,bool outbuffer_full) {
        if (!enabled_) return; VCWindow &x=vcw(r,p,v,t); ++x.sw_requests;
        if(no_credit) ++x.sw_blocked_no_credit; if(outbuffer_full) ++x.sw_blocked_outbuffer;
    }
    void sw_grant(long r,long p,long v,double t) { if(enabled_) ++vcw(r,p,v,t).sw_grants; }
    void crossbar(long r,double t) { if(enabled_) ++rw(r,t).crossbar_flits; }
    void link(long r,double t) { if(enabled_) ++rw(r,t).link_flits; }
    void dump(double final_time) {
        if (!enabled_) return;
        for (std::map<VCKey,QueueState>::iterator it=queue_state_.begin();it!=queue_state_.end();++it) integrate(it->first,it->second,final_time);
        std::ofstream vc((output_dir_+"/popnet_vc_microarch_windows.csv").c_str());
        vc << "window,window_start_cycle,window_end_cycle,router_id,port_id,vc_id,mean_queue_occupancy,max_queue_occupancy,active_fraction,queue_writes,queue_reads,vc_requests,vc_grants,vc_blocked_unavailable,sw_requests,sw_grants,sw_blocked_no_credit,sw_blocked_outbuffer,sw_arb_wait_opportunities\n";
        vc << std::setprecision(12);
        for (std::map<VCWindowKey,VCWindow>::const_iterator it=vc_windows_.begin();it!=vc_windows_.end();++it) {
            long r,p,v,w; std::tie(r,p,v,w)=it->first; const VCWindow &x=it->second;
            unsigned long long accounted=x.sw_grants+x.sw_blocked_no_credit+x.sw_blocked_outbuffer;
            unsigned long long wait=x.sw_requests>accounted?x.sw_requests-accounted:0;
            vc << w << ',' << w*window_cycles_ << ',' << (w+1)*window_cycles_ << ',' << r << ',' << p << ',' << v << ','
               << x.occupancy_cycle_sum/window_cycles_ << ',' << x.max_occupancy << ',' << x.active_cycle_sum/window_cycles_ << ','
               << x.queue_writes << ',' << x.queue_reads << ',' << x.vc_requests << ',' << x.vc_grants << ',' << x.vc_blocked_unavailable << ','
               << x.sw_requests << ',' << x.sw_grants << ',' << x.sw_blocked_no_credit << ',' << x.sw_blocked_outbuffer << ',' << wait << '\n';
        }
        std::ofstream rt((output_dir_+"/popnet_router_microarch_windows.csv").c_str());
        rt << "window,window_start_cycle,window_end_cycle,router_id,crossbar_flits,link_flits\n";
        for (std::map<RouterWindowKey,RouterWindow>::const_iterator it=router_windows_.begin();it!=router_windows_.end();++it)
            rt << it->first.second << ',' << it->first.second*window_cycles_ << ',' << (it->first.second+1)*window_cycles_ << ',' << it->first.first << ',' << it->second.crossbar_flits << ',' << it->second.link_flits << '\n';
        std::ofstream meta((output_dir_+"/popnet_microarch_metadata.txt").c_str());
        meta << "status=PASS\nwindow_cycles=" << window_cycles_ << "\nfinal_cycle=" << final_time << "\nvc_rows=" << vc_windows_.size() << "\nrouter_rows=" << router_windows_.size() << "\n";
    }
};

#endif

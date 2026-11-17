    struct PairPolicy {
        bool enabled=false, hiband=false;
        U local_budget=1536, global_budget=1536, used_local=0, used_global=0;
        U epoch=~U(0), packets=0, local_bytes=0, global_bytes=0, blocked=0;
        std::string mode="SHARED";

        void bind(U strategy, U local, U global) {
            need(!enabled&&strategy<=1&&local+global>0,"invalid paired NoC policy");
            enabled=true;
            hiband=strategy==1;
            if(!hiband)return;
            if(!global){mode="FULL_LOCAL";local_budget=1536;}
            else if(!local){mode="FULL_GLOBAL";local_budget=0;}
            else if(5*local>=3*(local+global)){mode="LOCAL_BIAS";local_budget=1024;}
            else{mode="GLOBAL_BIAS";local_budget=512;}
            global_budget=1536-local_budget;
        }

        bool issue(U tick, U bytes, bool local) {
            if(!enabled)return true;
            if(epoch!=tick){epoch=tick;used_local=used_global=0;}
            U& used=local?used_local:used_global;
            const U limit=local?local_budget:global_budget;
            need(bytes<=limit,"packet conflicts with frozen mode budget");
            if(used_local+used_global+bytes>1536||used+bytes>limit){++blocked;return false;}
            used+=bytes;
            ++packets;
            (local?local_bytes:global_bytes)+=bytes;
            return true;
        }

        void write(const std::string& out) const {
            if(!enabled)return;
            std::ofstream result(out+"/PAIRED_POLICY.json");
            result<<"{\"policy\":\""<<(hiband?"hiband_reference":"project_noc")<<"\",\"mode\":\""<<mode
                  <<"\",\"total_budget_bytes_per_tick\":1536,\"local_budget\":"<<local_budget
                  <<",\"global_budget\":"<<global_budget<<",\"admitted_packets\":"<<packets
                  <<",\"local_bytes\":"<<local_bytes<<",\"global_bytes\":"<<global_bytes
                  <<",\"budget_wait_events\":"<<blocked<<"}\n";
        }
    } pair_policy;

    bool paired_admit(int source,int destination,U flits){
        if(pair_policy.enabled){
            need(config.flit_size()*8==32,"paired native flit width changed");
            need(source>=0&&source<4&&destination>=0&&destination<4,"traffic escaped frozen single local stage");
        }
        return pair_policy.issue(cycle,flits*config.flit_size()*8,
                                 source>=0&&source<4&&destination>=0&&destination<4);
    }

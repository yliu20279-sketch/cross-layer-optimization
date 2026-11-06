#include "live_controls.h"
#include <functional>
#include <iostream>
int main() { try {
    using namespace p0live; int refused=0;
    auto reject=[&](std::function<void()> f) {bool failed=false;try{f();}catch(const std::runtime_error&){failed=true;}
        need(failed,"negative control was admitted");++refused;};
    AddressMap map({16384,16384});map.add(0,0,0,true);map.add(0,1,1,true);map.add(0,2,2,false);map.add(1,0,0,true);
    std::map<Page,uint64_t> swap{{{0,0},1},{{0,1},0},{{0,2},2},{{1,0},0}};
    map.install(swap,0);need(map.translate(0,4090,6,1)==8186,"map not applied");
    reject([&]{map.translate(0,4090,7,1);});reject([&]{map.translate(0,0,1,0);});
    reject([&]{auto bad=swap;bad[{0,2}]=0;bad[{0,1}]=2;map.install(bad,1);});
    reject([&]{auto bad=swap;bad[{0,1}]=1;map.install(bad,1);});
    reject([&]{auto bad=swap;bad[{0,0}]=4;map.install(bad,1);});
    map.accept(1,0,4090,6,1);reject([&]{map.install(swap,1);});
    reject([&]{map.callback(1,0);});map.callback(1,1);
    reject([&]{map.callback(1,1);});reject([&]{map.accept(1,0,4090,6,1);});
    map.install(swap,1);need(map.generation()==2&&map.inflight()==0,"map did not drain");
    LinkController c(10,3);need(c.local_budget()+c.global_budget()==1536,"budget total");
    auto a=c.accept(false,512,0);auto b=c.accept(false,512,0);
    need(!c.can_issue(false,1,0)&&!c.select(20,1,0),"budget/drain not enforced");
    c.callback(b,1);c.callback(a,2);need(c.select(20,1,2),"switch not executed");
    need(c.local_budget()==1024&&c.global_budget()==512&&!c.can_issue(true,1,4),"switch delay absent");
    need(!c.can_issue(false,1,5),"switch reused budget already spent in the same interval");
    auto p=c.accept(true,512,5);c.callback(p,6);reject([&]{c.callback(p,6);});
    reject([&]{c.can_issue(false,513,6);});reject([&]{c.can_issue(false,1,5);});
    std::cout<<"{\"status\":\"PASS_COMPILED_CONTROL_PROBE_ONLY\",\"rejected\":"<<refused
             <<",\"switches\":"<<c.switches<<",\"native_simulations\":0,\"model_forwards\":0}\n";
    return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;} }

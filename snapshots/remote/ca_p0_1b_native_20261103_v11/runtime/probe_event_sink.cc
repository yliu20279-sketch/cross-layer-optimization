#include "p0_event_sink.h"
#include <iostream>
#include <functional>
int main() {
    {std::ofstream f("objects.txt");f << "2\n0 0 4096 8192 0 1\n1 0 20000 32 0 0\n";}
    {std::ofstream f("requests.txt");f << "2\n0 profile_0\n1 profile_1\n";}
    p0::EventSink sink("events.jsonl","objects.txt","requests.txt","F16","profile");int rejected=0;
    auto refuses=[&](std::function<void()> fn){try{fn();}catch(const std::runtime_error&){++rejected;return;}throw std::runtime_error("negative not refused");};
    sink.accept(0,0,0,7,1,8186,20,false,0);
    sink.accept(1,0,0,8,1,8200,16,false,1);
    refuses([&]{sink.accept(0,0,0,7,1,8186,20,false,0);});
    refuses([&]{sink.finish();});
    refuses([&]{sink.callback(0,0,8,1,false,.5);});
    sink.callback(0,0,8,1,false,3);sink.callback(0,0,7,1,false,4);
    refuses([&]{sink.callback(0,0,7,1,false,5);});
    refuses([&]{sink.accept(0,0,0,7,1,8186,20,false,5);});
    refuses([&]{sink.accept(0,0,0,7,2,12287,2,false,5);});
    sink.accept(0,0,1,9,1,20000,16,false,5);sink.callback(0,1,9,1,false,6);
    sink.finish();p0::check(rejected==6,"wrong rejection count");
    std::cout << "{\"status\":\"PASS_CPP_EVENT_ABI_PROBE\",\"rejected\":"<<rejected<<",\"native_simulations\":0}\n";
}

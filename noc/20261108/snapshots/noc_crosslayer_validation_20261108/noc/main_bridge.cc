#include "configuration.h"
#include "sim_foundation.h"
#include "mess_queue.h"
#include "changes/aux_bridge.h"
#include "changes/dynamic_control.h"
#include "changes/receive_contract.h"
#include "changes/router_stalls.h"
#include "changes/receive_ready.h"
#include "changes/program_fences.h"
#include <iostream>
int main(int argc,char**argv) {
    try {
        SRGen random;
        configuration config(argc,argv);
        std::cout << config;
        mess_queue queue(TIME_0);
        sim_foundation network;
        ReceiveReady::get().start();
        DynamicControl::get().start();
        queue.simulator();
        AuxBridge::get().finish();
        DynamicControl::get().finish();
        WireProtocol::get().finish();
        ReceiveContract::get().finish();
        ReceiveReady::get().finish();
        ProgramFences::get().finish();
        RouterStalls::get().finish();
        network.simulation_results();
        return 0;
    } catch(const std::exception&e) {
        std::cerr<<"FAIL bridge: "<<e.what()<<'\n';return 1;
    }
}

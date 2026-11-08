#include "wire_protocol.h"
#include "aux_bridge.h"
#include "dynamic_control.h"
#include "../mess_queue.h"
#include "../sim_foundation.h"
#include "receive_contract.h"
#include "receive_ready.h"
#include <cstdlib>
#include <string>
#include <iomanip>

namespace {
void need(bool ok,const char* why){if(!ok)throw std::runtime_error(std::string("WIRE: ")+why);}
}
WireProtocol& WireProtocol::get(){static WireProtocol x;return x;}
WireProtocol::WireProtocol(){
    const char* p=std::getenv("NOC_DATA_WIRE");
    if(!p||!*p)return;
    need(std::string(p)=="1","NOC_DATA_WIRE must be 1 or unset");enabled_=true;
    need(std::getenv("NOC_AUX_CONFIG"),"wire mode requires the finite NI/AUX adapter");
    const char* fault=std::getenv("NOC_WIRE_FAULT");if(fault)fault_=fault;
    need(fault_.empty()||fault_=="type"||fault_=="source"||fault_=="padding"||fault_=="gateway"||fault_=="epoch","unknown explicit fault injection");
    log_.open("wire_headers.csv");need(bool(log_),"cannot open wire header log");
    log_<<std::setprecision(17);
    log_<<"time,event,node,packet,source,destination,gateway,aux,epoch,wire_word\n";
}
bool WireProtocol::is_control(const flit_template& f) const {
    if(!enabled_||!isHeader(f.type()))return false;
    need(f.data().size()==4,"not a 256-bit flit");
    unsigned type=unsigned(f.data()[3]>>61);
    if(type==5||type==6||type==7||(type==4&&ReceiveReady::get().enabled())){need(f.type()==SINGLE,"multi-flit control command");return true;}
    return false;
}
WireContext WireProtocol::decode(const flit_template& f) const {
    need(isHeader(f.type())&&f.data().size()==4,"expected actual header flit");
    WireContext c;c.valid=true;c.packet=f.getPacketId();c.start=f.start_time();
    c.control=is_control(f);
    if(c.control){
        unsigned d=unsigned((f.data()[3]>>57)&15);
        c.header={unsigned(f.sor_addr().front()),d,d,unsigned((f.data()[3]>>33)&65535),false};
    }else{
        noc::WireFlit data{{f.data()[0],f.data()[1],f.data()[2],f.data()[3]}};
        c.header=noc::decode(data);
    }
    need(f.sor_addr()==add_type{long(c.header.source)}&&
         f.des_addr()==add_type{long(c.header.destination)},"serialized source/final destination mismatch");
    return c;
}
bool WireProtocol::matches(const WireContext& c,const flit_template& f){
    return c.valid&&c.packet==f.getPacketId()&&c.start==f.start_time()&&
        f.sor_addr()==add_type{long(c.header.source)}&&f.des_addr()==add_type{long(c.header.destination)};
}
void WireProtocol::record(const char* event,long node,const flit_template& f,const WireContext& c){
    if(!enabled_)return;
    if(std::string(event)=="ROUTER")++router_headers_;
    log_<<mess_queue::m_pointer().current_time()<<','<<event<<','<<node<<','<<f.getPacketId()<<','
        <<c.header.source<<','<<c.header.destination<<','<<c.header.gateway<<','
        <<c.header.auxiliary<<','<<c.header.epoch<<','<<f.data()[3]<<'\n';
}
void WireProtocol::source(flit_template& f,bool provided_control){
    if(!enabled_)return;
    if(provided_control){
        need(is_control(f),"control frame must already contain a serialized header");
        auto c=decode(f);++control_headers_;record("SOURCE_CONTROL",f.sor_addr().front(),f,c);return;
    }
    long n=f.sor_addr().front();
    if(isHeader(f.type())){
        long gateway=f.des_addr().front();bool aux=AuxBridge::get().source_route(f,gateway);
        noc::DataHeader h{unsigned(n),unsigned(f.des_addr().front()),unsigned(gateway),
                         aux?unsigned(DynamicControl::get().active_epoch(n)):0,aux};
        if(ReceiveContract::get().enabled()){
            auto trans=sim_foundation::wsf().protoEngine().get_trans(f.getPacketId());
            // Source NI consumes the actual application WRITE descriptor.
            // Native protocol control flags retain Message ID zero.
            if(!(trans->protoDesc&0xF0000L))h.message_id=static_cast<std::uint64_t>(trans->protoDesc);
        }
        auto data=noc::encode(h);f.data().assign(data.begin(),data.end());
        source_[n]=decode(f);++source_headers_;record("SOURCE",n,f,source_[n]);
    }else{
        need(matches(source_[n],f)&&!source_[n].control,"body without local source packetization context");
        ++body_flits_;
    }
}
const WireContext& WireProtocol::source_context(const flit_template& f) const {
    const auto& c=source_[f.sor_addr().front()];need(matches(c,f),"source context mismatch");return c;
}
void WireProtocol::finish(){
    if(!enabled_)return;log_.flush();std::ofstream out("wire_summary.json");
    out<<"{\"serialized_data_headers\":"<<source_headers_<<",\"serialized_control_headers\":"<<control_headers_
       <<",\"router_header_decodes\":"<<router_headers_<<",\"unchanged_body_flits\":"<<body_flits_
       <<",\"router_uses_packet_table\":false,\"header_flit_bits\":256}\n";
}
void WireProtocol::fault_on_link(flit_template& f,long node){
    if(!enabled_||fault_.empty()||fault_applied_||!isHeader(f.type())||is_control(f)||
       f.getPacketId()!=0||node!=f.sor_addr().front())return;
    if(fault_=="padding")f.data()[0]^=1;
    else f.data()[3]^=std::uint64_t(1)<<(fault_=="type"?61:fault_=="source"?57:fault_=="gateway"?49:32);
    fault_applied_=true;record("FAULT",node,f,source_[node]);
}

#ifndef NOC_WIRE_PROTOCOL_H
#define NOC_WIRE_PROTOCOL_H
#include "data_header.h"
#include "../flit.h"
#include <array>
#include <fstream>
#include <string>

struct WireContext {
    bool valid=false,control=false;
    noc::DataHeader header;
    size_t packet=0;
    time_type start=0;
};

// Source packetization state and actual header decoding. Router contexts are
// separately held by each AuxGraphRouter's physical input/VC, not by packet ID.
class WireProtocol {
    bool enabled_=false;
    std::array<WireContext,16> source_{};
    std::ofstream log_;
    long source_headers_=0,control_headers_=0,router_headers_=0,body_flits_=0;
    std::string fault_;
    bool fault_applied_=false;
    WireProtocol();
public:
    static WireProtocol& get();
    bool enabled() const {return enabled_;}
    bool is_control(const flit_template&) const;
    WireContext decode(const flit_template&) const;
    static bool matches(const WireContext&,const flit_template&);
    void source(flit_template&,bool provided_control);
    const WireContext& source_context(const flit_template&) const;
    void record(const char*,long,const flit_template&,const WireContext&);
    void finish();
    void fault_on_link(flit_template&,long);
};
#endif

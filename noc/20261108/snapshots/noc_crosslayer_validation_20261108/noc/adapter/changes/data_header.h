#ifndef NOC_DATA_HEADER_20261106_H
#define NOC_DATA_HEADER_20261106_H
#include <array>
#include <cstdint>
#include <stdexcept>

// Candidate source-NI data header, not yet connected to the native adapter.
// The existing application trace already budgets one 256-bit header flit.
namespace noc {
struct DataHeader {
    unsigned source = 0, destination = 0, gateway = 0, epoch = 0;
    bool auxiliary = false;
    std::uint64_t message_id = 0; // Actual WRITE/READ matching tag; word 2.
};
using WireFlit = std::array<std::uint64_t, 4>; // atom 3 is bits 255:192.

inline void require_header(bool valid, const char* message) {
    if (!valid) throw std::invalid_argument(message);
}
inline void validate(const DataHeader& h) {
    require_header(h.source < 16 && h.destination < 16 && h.gateway < 16,
                   "node ID outside target's 16 nodes");
    require_header(h.epoch < 65536, "epoch exceeds 16 bits");
    if (h.auxiliary) {
        require_header(h.gateway != h.destination, "CS cannot return to the same corner");
    } else {
        require_header(h.gateway == h.destination && h.epoch == 0,
                       "ordinary Mesh header must use final destination and epoch zero");
    }
}
inline WireFlit encode(const DataHeader& h) {
    validate(h);
    const std::uint32_t bits = (std::uint32_t(h.source) << 25) |
        (std::uint32_t(h.destination) << 21) | (std::uint32_t(h.gateway) << 17) |
        (std::uint32_t(h.auxiliary) << 16) | std::uint32_t(h.epoch);
    return {{0, 0, h.message_id, std::uint64_t(bits) << 32}};
}
inline DataHeader decode(const WireFlit& f) {
    require_header(f[0] == 0 && f[1] == 0 && (f[3] & 0xffffffffULL) == 0,
                   "nonzero data-header padding");
    const std::uint32_t bits = std::uint32_t(f[3] >> 32);
    require_header((bits >> 29) == 0, "not a data header (Type must be 000)");
    DataHeader h{(bits >> 25) & 15, (bits >> 21) & 15, (bits >> 17) & 15,
                 bits & 65535, bool((bits >> 16) & 1)};
    validate(h);
    h.message_id=f[2];
    return h;
}
}
#endif

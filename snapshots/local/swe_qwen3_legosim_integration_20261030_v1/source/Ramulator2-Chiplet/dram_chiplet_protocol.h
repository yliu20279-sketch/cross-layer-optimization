#pragma once

#include <cstdint>

// The protocol intentionally uses fixed-size, byte-counted messages.  Pipe
// contents are only the functional transport; the paired readSync/writeSync
// calls are what make LEGOSim record timing traffic in bench.txt.
namespace DramChiplet {

// NPU-originated request ids are carried as the InterChiplet sync descriptor
// and therefore also survive the phase-2 PopNet replay.  Reserve a positive
// high-bit prefix so they cannot be confused with legacy small descriptors.
// Bits [47:44]/[43:40] encode NPU x/y and bits [39:20] are a local sequence.
// Bits [19:0] stay clear because InterChiplet reserves part of that range for
// synchronization-protocol flags (for example SPD_LAUNCH at bit 16).
constexpr std::uint64_t kNpuRequestIdMagic = 0x4E50000000000000ULL;
constexpr std::uint64_t kNpuRequestIdMagicMask = 0xFFFF000000000000ULL;

inline bool isNpuRequestId(std::uint64_t request_id) {
    return (request_id & kNpuRequestIdMagicMask) == kNpuRequestIdMagic;
}

enum class Operation : std::uint64_t {
    kStore = 1,
    kLoad = 2,
    kShutdown = 3,
};

struct Request {
    std::uint64_t operation = 0;
    std::uint64_t bytes = 0;
    std::uint64_t address = 0;
    std::uint64_t request_id = 0;
};

struct Reply {
    std::uint64_t request_id = 0;
    std::uint64_t status = 0;
};

static_assert(sizeof(Request) == 32, "DRAM request wire layout must stay stable");
static_assert(sizeof(Reply) == 16, "DRAM reply wire layout must stay stable");

}  // namespace DramChiplet

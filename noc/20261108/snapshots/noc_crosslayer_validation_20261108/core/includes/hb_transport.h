#pragma once
#include <cstdint>
#include <cstdlib>
#include <limits>
#include <stdexcept>
#include <string>

// Serialization occupancy of the existing one-client vertical interface.
// This is not a measured electrical flight latency. Every explicit RPC byte
// is charged; the RPC envelope is already included in its byte count.
namespace HbTransport {
inline bool enabled() {
    const bool bytes = std::getenv("LEGOSIM_HB_SERVICE_BYTES") != nullptr;
    const bool cycles = std::getenv("LEGOSIM_HB_SERVICE_CYCLES") != nullptr;
    if (bytes != cycles) throw std::runtime_error("both rational HB service fields required");
    return bytes;
}
inline std::uint64_t parameter(const char* key) {
    const char* p = std::getenv(key);
    if (!p || !*p) throw std::runtime_error("missing HB service parameter");
    std::uint64_t value = 0;
    for (; *p; ++p) {
        if (*p < '0' || *p > '9' ||
            value > (std::numeric_limits<std::uint64_t>::max() - (*p-'0')) / 10)
            throw std::runtime_error("invalid HB service parameter");
        value = value * 10 + (*p-'0');
    }
    if (!value) throw std::runtime_error("zero HB service parameter");
    return value;
}
inline std::uint64_t serialization(long bytes) {
    if (bytes <= 0 || !enabled()) throw std::runtime_error("invalid vertical byte count");
    const auto numerator = parameter("LEGOSIM_HB_SERVICE_CYCLES");
    const auto denominator = parameter("LEGOSIM_HB_SERVICE_BYTES");
    if (std::uint64_t(bytes) > std::numeric_limits<std::uint64_t>::max() / numerator)
        throw std::runtime_error("HB occupancy overflow");
    const auto product = std::uint64_t(bytes) * numerator;
    return product / denominator + (product % denominator != 0);
}
}

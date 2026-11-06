#pragma once

// Host-side tensor boundary codec shared by workload protocols and NPUSim.
// Functional tensors remain float on the host; this file defines the explicit
// FP32/FP16/BF16 conversion applied at chiplet communication and, optionally,
// at functional operator boundaries.

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace NPUSim {

// Values are stable on the wire.  Do not reorder them after a workload has
// been built, because TensorDescriptor carries the numeric value directly.
enum class TensorDType : std::int64_t {
    kFp32 = 1,
    kFp16 = 2,
    kBf16 = 3,
};

inline std::string toLowerAscii(std::string text) {
    for (char& ch : text) {
        if (ch >= 'A' && ch <= 'Z') {
            ch = static_cast<char>(ch - 'A' + 'a');
        }
    }
    return text;
}

inline TensorDType tensorDTypeFromString(const std::string& text) {
    const std::string value = toLowerAscii(text);
    if (value == "fp32" || value == "float" || value == "float32") {
        return TensorDType::kFp32;
    }
    if (value == "fp16" || value == "float16" || value == "half") {
        return TensorDType::kFp16;
    }
    if (value == "bf16" || value == "bfloat16") {
        return TensorDType::kBf16;
    }
    throw std::runtime_error("unsupported NPUSim tensor dtype '" + text +
                             "' (supported: fp32, fp16, bf16)");
}

inline const char* tensorDTypeName(TensorDType dtype) {
    switch (dtype) {
        case TensorDType::kFp32: return "fp32";
        case TensorDType::kFp16: return "fp16";
        case TensorDType::kBf16: return "bf16";
    }
    return "invalid";
}

inline std::size_t tensorDTypeBytes(TensorDType dtype) {
    switch (dtype) {
        case TensorDType::kFp32: return 4;
        case TensorDType::kFp16:
        case TensorDType::kBf16: return 2;
    }
    throw std::runtime_error("invalid NPUSim tensor dtype on wire");
}

inline bool isSupportedTensorDType(std::int64_t wire_value) {
    return wire_value == static_cast<std::int64_t>(TensorDType::kFp32) ||
           wire_value == static_cast<std::int64_t>(TensorDType::kFp16) ||
           wire_value == static_cast<std::int64_t>(TensorDType::kBf16);
}

inline TensorDType tensorDTypeFromWire(std::int64_t wire_value) {
    if (!isSupportedTensorDType(wire_value)) {
        throw std::runtime_error("unsupported NPUSim tensor dtype value " +
                                 std::to_string(wire_value));
    }
    return static_cast<TensorDType>(wire_value);
}

inline std::size_t checkedTensorByteCount(std::size_t elements, TensorDType dtype) {
    const std::size_t bytes_per_element = tensorDTypeBytes(dtype);
    if (elements > std::numeric_limits<std::size_t>::max() / bytes_per_element) {
        throw std::runtime_error("tensor payload byte count overflows size_t");
    }
    return elements * bytes_per_element;
}

inline std::uint32_t floatBits(float value) {
    std::uint32_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    return bits;
}

inline float floatFromBits(std::uint32_t bits) {
    float value = 0.0F;
    std::memcpy(&value, &bits, sizeof(value));
    return value;
}

// IEEE 754 binary32 -> binary16, round-to-nearest-even.  The result is sent
// little-endian as two bytes and does not rely on host support for __fp16.
inline std::uint16_t floatToFp16Bits(float value) {
    const std::uint32_t bits = floatBits(value);
    const std::uint32_t sign = (bits >> 16U) & 0x8000U;
    const std::uint32_t exponent = (bits >> 23U) & 0xFFU;
    std::uint32_t mantissa = bits & 0x7FFFFFU;

    if (exponent == 0xFFU) {
        // Preserve infinity; retain a non-zero quiet NaN payload for NaN.
        if (mantissa == 0) {
            return static_cast<std::uint16_t>(sign | 0x7C00U);
        }
        return static_cast<std::uint16_t>(sign | 0x7C00U | (mantissa >> 13U) | 0x0200U);
    }

    const int half_exponent = static_cast<int>(exponent) - 127 + 15;
    if (half_exponent >= 31) {
        return static_cast<std::uint16_t>(sign | 0x7C00U);
    }
    if (half_exponent <= 0) {
        if (half_exponent < -10) {
            return static_cast<std::uint16_t>(sign);
        }
        // Add the implicit leading one, shift to a FP16 subnormal, and round.
        mantissa |= 0x800000U;
        const unsigned shift = static_cast<unsigned>(14 - half_exponent);
        std::uint32_t half_mantissa = mantissa >> shift;
        const std::uint32_t remainder = mantissa & ((1U << shift) - 1U);
        const std::uint32_t halfway = 1U << (shift - 1U);
        if (remainder > halfway || (remainder == halfway && (half_mantissa & 1U) != 0)) {
            ++half_mantissa;
        }
        return static_cast<std::uint16_t>(sign | half_mantissa);
    }

    std::uint32_t half_mantissa = mantissa >> 13U;
    const std::uint32_t remainder = mantissa & 0x1FFFU;
    if (remainder > 0x1000U || (remainder == 0x1000U && (half_mantissa & 1U) != 0)) {
        ++half_mantissa;
    }
    // Carrying bit 10 of the mantissa into the assembled 16-bit word also
    // increments the exponent; it naturally becomes infinity at 0x7c00.
    return static_cast<std::uint16_t>(sign |
                                      (static_cast<std::uint32_t>(half_exponent) << 10U) |
                                      half_mantissa);
}

inline float fp16BitsToFloat(std::uint16_t bits) {
    const std::uint32_t sign = static_cast<std::uint32_t>(bits & 0x8000U) << 16U;
    int exponent = static_cast<int>((bits >> 10U) & 0x1FU);
    std::uint32_t mantissa = bits & 0x03FFU;
    std::uint32_t out_bits = 0;
    if (exponent == 0) {
        if (mantissa == 0) {
            out_bits = sign;
        } else {
            exponent = 1;
            while ((mantissa & 0x0400U) == 0) {
                mantissa <<= 1U;
                --exponent;
            }
            out_bits = sign | (static_cast<std::uint32_t>(exponent + 112) << 23U) |
                       ((mantissa & 0x03FFU) << 13U);
        }
    } else if (exponent == 31) {
        out_bits = sign | 0x7F800000U | (mantissa << 13U);
    } else {
        out_bits = sign | (static_cast<std::uint32_t>(exponent + 112) << 23U) |
                   (mantissa << 13U);
    }
    return floatFromBits(out_bits);
}

inline std::uint16_t floatToBf16Bits(float value) {
    const std::uint32_t bits = floatBits(value);
    // Round-to-nearest-even.  Do not turn an existing NaN into infinity.
    const std::uint32_t exponent = bits & 0x7F800000U;
    const std::uint32_t mantissa = bits & 0x007FFFFFU;
    std::uint32_t rounded = bits;
    if (!(exponent == 0x7F800000U && mantissa != 0)) {
        rounded += 0x7FFFU + ((bits >> 16U) & 1U);
    }
    std::uint16_t result = static_cast<std::uint16_t>(rounded >> 16U);
    if (exponent == 0x7F800000U && mantissa != 0 && (result & 0x007FU) == 0) {
        result = static_cast<std::uint16_t>(result | 0x0040U);
    }
    return result;
}

inline float bf16BitsToFloat(std::uint16_t bits) {
    return floatFromBits(static_cast<std::uint32_t>(bits) << 16U);
}

inline void appendU16LittleEndian(std::vector<std::uint8_t>& output, std::uint16_t value) {
    output.push_back(static_cast<std::uint8_t>(value & 0xFFU));
    output.push_back(static_cast<std::uint8_t>((value >> 8U) & 0xFFU));
}

inline std::uint16_t readU16LittleEndian(const std::uint8_t* input) {
    return static_cast<std::uint16_t>(static_cast<std::uint16_t>(input[0]) |
                                      (static_cast<std::uint16_t>(input[1]) << 8U));
}

inline std::vector<std::uint8_t> encodeFloatTensor(const std::vector<float>& values,
                                                    TensorDType dtype) {
    std::vector<std::uint8_t> output;
    output.reserve(checkedTensorByteCount(values.size(), dtype));
    for (float value : values) {
        switch (dtype) {
            case TensorDType::kFp32: {
                const std::uint32_t bits = floatBits(value);
                output.push_back(static_cast<std::uint8_t>(bits & 0xFFU));
                output.push_back(static_cast<std::uint8_t>((bits >> 8U) & 0xFFU));
                output.push_back(static_cast<std::uint8_t>((bits >> 16U) & 0xFFU));
                output.push_back(static_cast<std::uint8_t>((bits >> 24U) & 0xFFU));
                break;
            }
            case TensorDType::kFp16:
                appendU16LittleEndian(output, floatToFp16Bits(value));
                break;
            case TensorDType::kBf16:
                appendU16LittleEndian(output, floatToBf16Bits(value));
                break;
        }
    }
    return output;
}

inline std::vector<float> decodeFloatTensor(const std::vector<std::uint8_t>& payload,
                                             TensorDType dtype) {
    const std::size_t bytes_per_element = tensorDTypeBytes(dtype);
    if (payload.size() % bytes_per_element != 0) {
        throw std::runtime_error("tensor payload is not aligned to its dtype width");
    }
    std::vector<float> output;
    output.reserve(payload.size() / bytes_per_element);
    for (std::size_t offset = 0; offset < payload.size(); offset += bytes_per_element) {
        switch (dtype) {
            case TensorDType::kFp32: {
                const std::uint32_t bits = static_cast<std::uint32_t>(payload[offset]) |
                    (static_cast<std::uint32_t>(payload[offset + 1]) << 8U) |
                    (static_cast<std::uint32_t>(payload[offset + 2]) << 16U) |
                    (static_cast<std::uint32_t>(payload[offset + 3]) << 24U);
                output.push_back(floatFromBits(bits));
                break;
            }
            case TensorDType::kFp16:
                output.push_back(fp16BitsToFloat(readU16LittleEndian(payload.data() + offset)));
                break;
            case TensorDType::kBf16:
                output.push_back(bf16BitsToFloat(readU16LittleEndian(payload.data() + offset)));
                break;
        }
    }
    return output;
}

// Storage-precision emulation for the FP32 host functional path.  Arithmetic
// itself is still host FP32; values are rounded at the chosen tensor boundary.
inline float convertFloatForTensorDType(float value, TensorDType dtype) {
    switch (dtype) {
        case TensorDType::kFp32: return value;
        case TensorDType::kFp16: return fp16BitsToFloat(floatToFp16Bits(value));
        case TensorDType::kBf16: return bf16BitsToFloat(floatToBf16Bits(value));
    }
    throw std::runtime_error("invalid NPUSim tensor dtype during conversion");
}

inline void convertFloatTensorInPlace(std::vector<float>& values, TensorDType dtype) {
    if (dtype == TensorDType::kFp32) {
        return;
    }
    for (float& value : values) {
        value = convertFloatForTensorDType(value, dtype);
    }
}

}  // namespace NPUSim

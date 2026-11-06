#pragma once

#include <cstdint>

#include "npusim_tensor_codec.h"

// CPU 与 NPU 两个独立进程共享的最小控制协议。
// tensor 本体始终留在共享 DRAM；这里仅传 token、shape、dtype、地址和字节数。
// 所有字段均为固定宽度整数，避免不同编译器/ABI 的结构体布局不一致。
namespace CpuNpuOnnxProtocol {

constexpr std::int64_t kStartToken = 1;
constexpr std::int64_t kOutputConsumedToken = 2;
constexpr std::int64_t kSuccess = 1;
constexpr std::int64_t kTensorDTypeFp32 = static_cast<std::int64_t>(NPUSim::TensorDType::kFp32);
constexpr std::int64_t kTensorDTypeFp16 = static_cast<std::int64_t>(NPUSim::TensorDType::kFp16);
constexpr std::int64_t kTensorDTypeBf16 = static_cast<std::int64_t>(NPUSim::TensorDType::kBf16);

struct NpuTaskDescriptor {
    // kStartToken 请求一次 ONNX 推理；后面紧跟 input_count 个描述符，
    // 每个描述符指向已经由 CPU 写入共享 DRAM 的输入 tensor。
    std::int64_t token = 0;
    std::int64_t input_count = 0;
};

struct DramTensorDescriptor {
    // tensor 的“位置描述”，而非 tensor 数据。dtype 使用 npusim_tensor_codec 的 wire 值。
    std::int64_t rank = 0;
    std::int64_t element_count = 0;
    std::int64_t dtype = kTensorDTypeFp32;
    std::int64_t dram_address = 0;
    std::int64_t byte_count = 0;
};

struct NpuCompletion {
    // 1 表示 ONNX timing 已将全部图输出写入共享 DRAM。
    std::int64_t status = 0;
    std::int64_t event_count = 0;
    // NPU 模拟时钟中，所有输出 DMA_STORE 已完成、可通知 CPU 的周期。
    std::int64_t finish_cycle = 0;
    std::int64_t output_count = 0;
};

// CPU 将所有输出从共享 DRAM 读完后发回 ACK，NPU 才能关闭 DRAM server；
// 否则单客户端 server 可能在 CPU LOAD 前退出。
struct OutputConsumedAck {
    std::int64_t token = 0;
};

struct TensorDescriptor {
    std::int64_t rank = 0;
    std::int64_t element_count = 0;
    // Wire dtype: FP32 / IEEE FP16 / BF16。payload 明确为 little-endian，
    // 两端不交换与编译器相关的 half 对象。
    std::int64_t dtype = kTensorDTypeFp32;
};

static_assert(sizeof(NpuTaskDescriptor) == 2 * sizeof(std::int64_t),
              "CPU/NPU task protocol must not contain padding");
static_assert(sizeof(NpuCompletion) == 4 * sizeof(std::int64_t),
              "CPU/NPU completion protocol must not contain padding");
static_assert(sizeof(DramTensorDescriptor) == 5 * sizeof(std::int64_t),
              "CPU/NPU DRAM tensor descriptor must not contain padding");
static_assert(sizeof(TensorDescriptor) == 3 * sizeof(std::int64_t),
              "CPU/NPU tensor descriptor must not contain padding");
static_assert(sizeof(OutputConsumedAck) == sizeof(std::int64_t),
              "CPU/NPU output-consumed acknowledgement must not contain padding");

}  // namespace CpuNpuOnnxProtocol

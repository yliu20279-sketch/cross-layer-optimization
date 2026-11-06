#pragma once

#include <cstdint>
#include <map>
#include <string>
#include <vector>

#include "npusim_runtime.h"

namespace NPUSim {

// Controls the conservative, graph-level memory mapping used by the ONNX
// event lowerer.  Every non-view operator materializes its output in the
// activation region, so the generated DMA stream is valid before a later
// SRAM/liveness allocator is introduced.
struct OnnxEventLoweringOptions {
    std::uint64_t activation_base_address = 0x10000000ULL;
    std::uint64_t weight_base_address = 0x80000000ULL;
    std::uint64_t address_alignment_bytes = 64;
    // A CPU/IO producer may select the shared-DRAM address of an ONNX graph
    // input.  The lowerer then emits its consuming DMA_LOAD from exactly that
    // address instead of allocating a private timing-only activation slot.
    std::map<std::string, std::uint64_t> tensor_address_overrides;
    bool fail_on_unsupported_operator = true;
};

struct OnnxEventLoweringResult {
    std::vector<NpuProgramEvent> events;
    std::map<std::string, std::vector<std::int64_t>> inferred_value_shapes;
    std::map<std::string, std::uint64_t> tensor_addresses;
    // The completion event for each materialized tensor.  Graph inputs and
    // initializers have no producer event and are therefore absent.
    std::map<std::string, NpuEventId> tensor_ready_events;
    std::vector<std::string> unsupported_operators;
};

// Lowers a parsed, statically-shaped ONNX graph into the generic NPU event
// vocabulary.  Supported compute classes include MAC (MatMul/Gemm/Conv),
// vector, reduction, Softmax and RMSNormalization.  This function performs
// no functional tensor execution and no timing itself; callers schedule the
// returned events with scheduleNpuProgramEvents and their DRAM callback.
OnnxEventLoweringResult lowerOnnxModelToProgramEvents(
    const Model& model,
    const NPUConfig& config,
    const OnnxEventLoweringOptions& options = OnnxEventLoweringOptions{});

// Convenience entry point for an ONNX byte payload.  It deliberately uses
// NPUSim's parser boundary, so the lowerer remains independent of whether the
// Model came from the current lightweight parser or a future official ONNX
// protobuf loader.
OnnxEventLoweringResult lowerOnnxBytesToProgramEvents(
    const std::vector<char>& model_bytes,
    const NPUConfig& config,
    const OnnxEventLoweringOptions& options = OnnxEventLoweringOptions{});

}  // namespace NPUSim

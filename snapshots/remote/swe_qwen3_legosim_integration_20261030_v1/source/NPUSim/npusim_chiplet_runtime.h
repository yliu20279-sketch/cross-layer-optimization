#pragma once

#include "npusim_chiplet_memory.h"

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace NPUSim {

// Runtime-wide settings which are independent of an individual NPU operator.
// A LEGOSim C++ workload provides these once when its NPU process starts;
// operator code then only records primitives or uses a native tile plan.
struct ChipletNpuRuntimeOptions {
    int self_x = 0;
    int self_y = 0;
    unsigned long long initial_cycle = 1;

    // If transaction_trace_path is empty and report_directory is supplied, a
    // stable per-NPU trace name is generated below that directory.
    std::string report_directory;
    std::string transaction_trace_path;
    // Offline NPU-intra PopNet delay profile.  This is separate from any DRAM
    // memory-modeling path and only affects controller<->MAC timing.
    std::string intra_delay_profile_path;
    std::string log_prefix = "[NPUSIM][DRAM]";
    std::uint64_t trace_base_address = 0;
};

// Owns the reusable chiplet-facing part of a C++ NPU workload: the simulated
// clock, DRAM-chiplet client, transaction trace and the DMA callback passed
// to NPUSim's schedulers.  It deliberately does not own tensor values,
// addresses or an operator-specific lowering policy.
class ChipletNpuRuntime {
  public:
    ChipletNpuRuntime(const NPUConfig& config,
                      const ChipletNpuRuntimeOptions& options = ChipletNpuRuntimeOptions{});
    ~ChipletNpuRuntime();

    ChipletNpuRuntime(const ChipletNpuRuntime&) = delete;
    ChipletNpuRuntime& operator=(const ChipletNpuRuntime&) = delete;

    const NPUConfig& config() const;
    unsigned long long& chipCycle();
    const std::vector<ChipletDramCompletionRecord>& dramCompletions() const;

    // Functional tensor materialisation.  The external-memory requests are
    // emitted by the shared NPUSim client rather than by workload-local code.
    void store(std::uint64_t address,
               const void* data,
               std::size_t bytes,
               const std::string& label);
    void load(std::uint64_t address,
              void* data,
              std::size_t bytes,
              const std::string& label);

    // Generic C++/ONNX lowering path.  A DMA event returns data-ready only
    // after the chiplet request/response.
    NpuProgramScheduleResult scheduleProgram(
        const std::vector<NpuProgramEvent>& events,
        const ChipletDmaCallbackOptions& dma_options = ChipletDmaCallbackOptions{});

    // Native tile planner path, currently used by rank-2 MatMul.  The same
    // DMA client produces tile data-ready times and prevents a workload from
    // recreating a second MAC/DMA scheduler.
    NpuTileScheduleResult scheduleTiles(
        const std::vector<NpuTileEvent>& tiles,
        std::uint64_t injected_intra_cycles,
        const ChipletDmaCallbackOptions& dma_options = ChipletDmaCallbackOptions{});

    void shutdown();

  private:
    NPUConfig config_;
    unsigned long long chip_cycle_ = 1;
    IntraDelayProfile intra_delay_profile_;
    std::unique_ptr<ChipletMemoryClient> memory_;
};

}  // namespace NPUSim

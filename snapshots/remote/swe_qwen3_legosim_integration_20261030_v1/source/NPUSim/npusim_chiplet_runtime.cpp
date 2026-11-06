#include "npusim_chiplet_runtime.h"

#include <algorithm>
#include <stdexcept>
#include <utility>

namespace NPUSim {
namespace {

std::string defaultTransactionTrace(const ChipletNpuRuntimeOptions& options) {
    if (!options.transaction_trace_path.empty()) {
        return options.transaction_trace_path;
    }
    if (options.report_directory.empty()) {
        return {};
    }
    return options.report_directory + "/npusim_dram_transactions_" +
           std::to_string(options.self_x) + "_" + std::to_string(options.self_y) + ".csv";
}

}  // namespace

ChipletNpuRuntime::ChipletNpuRuntime(const NPUConfig& config,
                                     const ChipletNpuRuntimeOptions& options)
    : config_(config), chip_cycle_(options.initial_cycle) {
    if (!config_.external_memory_enable || config_.external_memory_model != "chiplet") {
        throw std::runtime_error(
            "ChipletNpuRuntime requires external_memory.enable=true and external_memory.model=chiplet");
    }
    ChipletMemoryClientOptions memory_options;
    memory_options.self_x = options.self_x;
    memory_options.self_y = options.self_y;
    memory_options.transaction_trace_path = defaultTransactionTrace(options);
    memory_options.log_prefix = options.log_prefix;
    memory_options.trace_base_address = options.trace_base_address;
    memory_ = std::make_unique<ChipletMemoryClient>(config_, memory_options, chip_cycle_);
    if (config_.intra_delay_enable) {
        if (options.intra_delay_profile_path.empty()) {
            throw std::runtime_error(
                "NPU intra delay is enabled but no intra_delay_profile_path was supplied; "
                "run make cpp-intra-delay or make onnx-intra-delay first");
        }
        intra_delay_profile_ = loadIntraDelayProfile(options.intra_delay_profile_path);
        if (!intra_delay_profile_.loaded || intra_delay_profile_.task_dst_delay.empty()) {
            throw std::runtime_error(
                "cannot load NPU intra delay profile: " + options.intra_delay_profile_path);
        }
    }
}

ChipletNpuRuntime::~ChipletNpuRuntime() = default;

const NPUConfig& ChipletNpuRuntime::config() const {
    return config_;
}

unsigned long long& ChipletNpuRuntime::chipCycle() {
    return chip_cycle_;
}

const std::vector<ChipletDramCompletionRecord>& ChipletNpuRuntime::dramCompletions() const {
    return memory_->completionRecords();
}

void ChipletNpuRuntime::store(std::uint64_t address,
                              const void* data,
                              std::size_t bytes,
                              const std::string& label) {
    memory_->store(address, data, bytes, label);
}

void ChipletNpuRuntime::load(std::uint64_t address,
                             void* data,
                             std::size_t bytes,
                             const std::string& label) {
    memory_->load(address, data, bytes, label);
}

NpuProgramScheduleResult ChipletNpuRuntime::scheduleProgram(
    const std::vector<NpuProgramEvent>& events,
    const ChipletDmaCallbackOptions& dma_options) {
    const auto request_completion_resolver = [this](std::uint64_t request_id)
        -> std::optional<std::uint64_t> {
        const std::optional<ChipletDramCompletionRecord> completion =
            memory_->findCompletion(request_id);
        if (!completion.has_value()) {
            return std::nullopt;
        }
        return completion->complete_cycle;
    };
    const NpuProgramScheduleResult result = scheduleNpuProgramEvents(
        events,
        config_,
        chip_cycle_,
        memory_->makeTraceDmaCallback(dma_options),
        config_.intra_delay_enable ? &intra_delay_profile_ : nullptr,
        request_completion_resolver);
    chip_cycle_ = std::max<unsigned long long>(chip_cycle_, result.overall_finish_cycle);
    return result;
}

NpuTileScheduleResult ChipletNpuRuntime::scheduleTiles(
    const std::vector<NpuTileEvent>& tiles,
    std::uint64_t injected_intra_cycles,
    const ChipletDmaCallbackOptions& dma_options) {
    const NpuTileScheduleResult result = scheduleNpuTileEvents(
        tiles,
        config_,
        chip_cycle_,
        injected_intra_cycles,
        memory_->makeTraceDmaCallback(dma_options));
    chip_cycle_ = std::max<unsigned long long>(chip_cycle_, result.overall_finish_cycle);
    return result;
}

void ChipletNpuRuntime::shutdown() {
    memory_->shutdown();
}

}  // namespace NPUSim

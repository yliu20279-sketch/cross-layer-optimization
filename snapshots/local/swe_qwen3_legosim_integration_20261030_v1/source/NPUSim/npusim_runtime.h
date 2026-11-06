#pragma once

#include <cstdint>
#include <functional>
#include <map>
#include <optional>
#include <string>
#include <vector>

#include "npusim_tensor_codec.h"

namespace NPUSim {

struct NPUConfig {
    int mac_unit_count = 16;
    int rows = 4;
    int cols = 4;
    int controller_local_id = 16;
    int topology_node_count = 0;
    std::string topology_mode = "custom_gv";
    std::string topology_gv_path;
    std::vector<int> mac_nodes;
    std::uint64_t sram_per_mac_bytes = 128ULL * 1024ULL;
    std::uint64_t activation_bytes = 4;
    std::uint64_t weight_bytes = 4;
    std::uint64_t accumulator_bytes = 4;
    std::uint64_t output_bytes = 4;
    // Explicit storage/transport formats.  Byte widths continue to drive the
    // timing model, while these fields drive numerical boundary conversion and
    // CPU<->NPU payload encoding.  A config that omits them remains FP32 for
    // functional/protocol data, preserving legacy behaviour.
    TensorDType activation_dtype = TensorDType::kFp32;
    TensorDType weight_dtype = TensorDType::kFp32;
    TensorDType accumulator_dtype = TensorDType::kFp32;
    TensorDType output_dtype = TensorDType::kFp32;
    bool activation_dtype_explicit = false;
    bool weight_dtype_explicit = false;
    bool accumulator_dtype_explicit = false;
    bool output_dtype_explicit = false;
    bool functional_round_each_operator = true;
    bool onnx_materialize_weights_to_dram = false;
    int mac_array_rows = 4;
    int mac_array_cols = 4;
    int tile_m = 0;
    int tile_n = 0;
    int tile_k = 0;
    std::uint64_t mac_ops_per_cycle = 400;
    // Resource-level throughput for generic NPU program events.  These are
    // deliberately separate from MAC throughput: element-wise and reduction
    // work do not consume the systolic MAC array in this model.
    std::uint64_t vector_ops_per_cycle = 128;
    std::uint64_t reduce_ops_per_cycle = 64;
    std::uint64_t sram_bandwidth_bytes_per_cycle = 64;
    std::uint64_t ddr_bandwidth_bytes_per_cycle = 64;
    std::uint64_t memory_unit_bytes = 128ULL * 1024ULL;
    std::uint64_t sram_miss_penalty_cycles = 120;
    std::uint64_t pipeline_depth_cycles = 16;
    std::uint64_t flit_payload_bytes = 32;
    bool intra_delay_enable = true;
    double intra_delay_scale = 1.0;
    std::string compute_memory_mode = "sum";
    bool external_memory_enable = false;
    std::string external_memory_model = "analytic";
    std::uint64_t dram_transaction_bytes = 64;
    std::uint64_t dram_read_fixed_latency_cycles = 80;
    std::uint64_t dram_write_fixed_latency_cycles = 80;
    double dram_cycle_scale = 1.0;
    std::uint64_t dram_size_bytes = 128ULL * 1024ULL * 1024ULL;
    // Used only when external_memory.model is "chiplet".  The service time then
    // belongs to a separate LEGOSim DRAM process rather than to NPUSim.
    int dram_chiplet_x = -1;
    int dram_chiplet_y = -1;
    std::uint64_t dram_chiplet_burst_bytes = 4096;
    std::uint64_t dram_chiplet_region_bytes = 8ULL * 1024ULL * 1024ULL;
    int dram_chiplet_grid_cols = 1;
};

struct MacTopologyInfo {
    int mac_id = 0;
    int node_id = 0;
    int degree = 0;
    std::uint64_t distance_to_controller = 0;
    std::uint64_t sram_bytes = 0;
    std::uint64_t ops_per_cycle = 0;
};

struct TopologyInfo {
    int node_count = 0;
    int controller_node = 0;
    std::string gv_path;
    std::vector<MacTopologyInfo> macs;
};

struct Tensor {
    std::vector<std::int64_t> shape;
    std::vector<float> data;
    // ONNX shape/axis/indices constants are stored in the same float host
    // container for historical reasons.  Keep their integer meaning so a
    // BF16/FP16 functional storage model never rounds a Reshape shape such as
    // 513 into a different value.
    bool integer_semantics = false;

    std::size_t elements() const;
};

// Functional ONNX execution is intentionally separate from the NPU timing
// scheduler.  A chiplet wrapper runs this reference path in parallel with
// ChipletNpuRuntime::scheduleProgram(), then transmits data only after both
// the tensor and the modeled timing completion are ready.
struct FunctionalOnnxResult {
    std::vector<Tensor> output_tensors;
    std::map<std::string, Tensor> named_tensors;
};

// Functional execution uses host FP32 arithmetic but can round values at the
// same tensor boundaries as the modeled NPU.  This is not a bit-accurate MAC
// accumulator model: accumulator rounding within a dot product still needs a
// dedicated microarchitecture implementation if a paper requires it.
struct FunctionalOnnxExecutionOptions {
    TensorDType activation_dtype = TensorDType::kFp32;
    TensorDType weight_dtype = TensorDType::kFp32;
    TensorDType accumulator_dtype = TensorDType::kFp32;
    TensorDType output_dtype = TensorDType::kFp32;
    bool round_each_operator = true;
};

struct Node {
    std::string name;
    std::string op_type;
    std::vector<std::string> inputs;
    std::vector<std::string> outputs;
    std::map<std::string, std::int64_t> int_attrs;
    std::map<std::string, float> float_attrs;
    std::map<std::string, std::vector<std::int64_t>> ints_attrs;
    std::map<std::string, Tensor> tensor_attrs;
};

struct Model {
    std::vector<Node> nodes;
    std::map<std::string, Tensor> initializers;
    std::map<std::string, std::vector<std::int64_t>> value_shapes;
    std::vector<std::string> graph_inputs;
    std::vector<std::string> graph_outputs;
};

struct MacUnitReport {
    int mac_id = 0;
    int node_id = 0;
    std::uint64_t ops = 0;
    std::uint64_t bytes = 0;
    std::uint64_t compute_cycles = 0;
    std::uint64_t memory_cycles = 0;
    std::uint64_t total_cycles = 0;
    std::uint64_t spm_read_accesses = 0;
    std::uint64_t spm_write_accesses = 0;
    std::uint64_t spm_miss_accesses = 0;
    std::uint64_t spm_read_bytes = 0;
    std::uint64_t spm_write_bytes = 0;
    std::uint64_t input_read_bytes = 0;
    std::uint64_t weight_read_bytes = 0;
    std::uint64_t psum_read_bytes = 0;
    std::uint64_t psum_write_bytes = 0;
    std::uint64_t output_write_bytes = 0;
    std::uint64_t ddr_read_bytes = 0;
    std::uint64_t ddr_write_bytes = 0;
    std::uint64_t dram_read_transactions = 0;
    std::uint64_t dram_write_transactions = 0;
    std::uint64_t dram_cycles = 0;
    std::uint64_t tile_count = 0;
    double array_utilization = 1.0;
};

struct NodeReport {
    std::string name;
    std::string op_type;
    std::uint64_t ops = 0;
    std::uint64_t bytes = 0;
    std::uint64_t compute_cycles = 0;
    std::uint64_t memory_cycles = 0;
    std::uint64_t injected_intra_cycles = 0;
    std::uint64_t total_cycles = 0;
    std::uint64_t spm_read_accesses = 0;
    std::uint64_t spm_write_accesses = 0;
    std::uint64_t spm_miss_accesses = 0;
    std::uint64_t spm_read_bytes = 0;
    std::uint64_t spm_write_bytes = 0;
    std::uint64_t input_read_bytes = 0;
    std::uint64_t weight_read_bytes = 0;
    std::uint64_t psum_read_bytes = 0;
    std::uint64_t psum_write_bytes = 0;
    std::uint64_t output_write_bytes = 0;
    std::uint64_t ddr_read_bytes = 0;
    std::uint64_t ddr_write_bytes = 0;
    std::uint64_t dram_read_transactions = 0;
    std::uint64_t dram_write_transactions = 0;
    std::uint64_t dram_cycles = 0;
    std::uint64_t tile_count = 0;
    double array_utilization = 1.0;
    int active_macs = 0;
    std::vector<MacUnitReport> mac_units;
};

struct NpuTileEvent {
    std::uint64_t op_desc = 0;
    std::uint64_t tile_id = 0;
    int mac_id = 0;
    int node_id = 0;
    std::uint64_t ops = 0;
    std::uint64_t ddr_read_bytes = 0;
    std::uint64_t ddr_write_bytes = 0;
    std::uint64_t compute_cycles = 0;
    std::uint64_t local_memory_cycles = 0;
};

struct RunResult {
    std::vector<std::int64_t> output_i64;// Convert primary output to int64 after rounding
    std::vector<Tensor> output_tensors;
    std::vector<NodeReport> node_reports;
    std::uint64_t compute_cycles = 0;
    std::uint64_t injected_intra_cycles = 0;
    std::uint64_t total_cycles = 0;
    std::uint64_t emitted_packets = 0;
    std::uint64_t ddr_read_bytes = 0;
    std::uint64_t ddr_write_bytes = 0;
    std::uint64_t dram_read_transactions = 0;
    std::uint64_t dram_write_transactions = 0;
    std::uint64_t dram_cycles = 0;
    // Extra end-to-end time supplied by an external DRAM chiplet adapter.
    // This remains zero for analytic runs.
    std::uint64_t chiplet_memory_cycles = 0;
    std::uint64_t tile_scheduled_cycles = 0;
    // Generic per-op/per-MAC execution descriptors.  They are runtime data,
    // not JSON payloads; adapters can consume them to emit physical DMA traffic
    // without re-implementing NPU tiling or MAC scheduling.
    std::vector<NpuTileEvent> tile_events;
    std::uint64_t end_to_end_cycles = 0;
};

// Kept as a source-compatible alias for existing direct-MatMul callers.
using MatMulTileEvent = NpuTileEvent;

struct NpuMemoryRequest {
    std::uint64_t logical_id = 0;
    std::uint64_t op_desc = 0;
    std::uint64_t tile_id = 0;
    int mac_id = 0;
    bool is_write = false;
    std::uint64_t bytes = 0;
    // Optional byte address.  Legacy tiled MatMul events leave it zero;
    // generic program events preserve the workload-provided address so a
    // DRAM-chiplet adapter can map traffic without reconstructing the op.
    std::uint64_t address = 0;
};

struct NpuTileScheduleEntry {
    NpuTileEvent tile;
    std::uint64_t read_issue_cycle = 0;
    std::uint64_t data_ready_cycle = 0;
    std::uint64_t mac_start_cycle = 0;
    std::uint64_t mac_finish_cycle = 0;
    std::uint64_t write_issue_cycle = 0;
    std::uint64_t write_complete_cycle = 0;
};

struct NpuTileScheduleResult {
    std::uint64_t finish_cycle = 0;
    std::uint64_t max_mac_finish_cycle = 0;
    std::uint64_t dma_finish_cycle = 0;
    std::uint64_t external_finish_cycle = 0;
    std::uint64_t overall_finish_cycle = 0;
    std::uint64_t injected_intra_cycles = 0;
    std::vector<NpuTileScheduleEntry> entries;
};

using NpuMemoryTransferCallback =
    std::function<std::uint64_t(const NpuMemoryRequest&, std::uint64_t issue_cycle)>;

using NpuRequestCompletionResolver =
    std::function<std::optional<std::uint64_t>(std::uint64_t request_id)>;

// A generic workload records hardware primitives, rather than one simulator
// API for every high-level neural-network operator.  For example, RMSNorm
// lowers to DMA + vector + reduce events, while QK^T lowers to DMA + MAC
// events.  Event dependencies represent data readiness and must refer to
// events recorded earlier in the stream.
using NpuEventId = std::uint64_t;

enum class NpuProgramEventKind {
    kDmaLoad,
    kDmaStore,
    kMacCompute,
    kVectorCompute,
    kReduceCompute,
    kBarrier,
};

struct NpuProgramEvent {
    NpuEventId id = 0;
    std::uint64_t op_desc = 0;
    NpuProgramEventKind kind = NpuProgramEventKind::kBarrier;
    int mac_id = -1;  // Required only for kMacCompute.
    std::uint64_t address = 0;  // Required only for DMA events.
    std::uint64_t bytes = 0;    // Required only for DMA events.
    std::uint64_t ops = 0;      // Required only for compute events.
    std::vector<NpuEventId> dependencies;
    std::vector<std::uint64_t> wait_request_ids;
};

class NpuEventRecorder {
public:
    NpuEventId dmaLoad(std::uint64_t op_desc,
                       std::uint64_t address,
                       std::uint64_t bytes,
                       const std::vector<NpuEventId>& dependencies = {});
    NpuEventId dmaStore(std::uint64_t op_desc,
                        std::uint64_t address,
                        std::uint64_t bytes,
                        const std::vector<NpuEventId>& dependencies = {});
    NpuEventId macCompute(std::uint64_t op_desc,
                          std::uint64_t ops,
                          int mac_id,
                          const std::vector<NpuEventId>& dependencies = {});
    NpuEventId vectorCompute(std::uint64_t op_desc,
                             std::uint64_t ops,
                             const std::vector<NpuEventId>& dependencies = {});
    NpuEventId reduceCompute(std::uint64_t op_desc,
                             std::uint64_t ops,
                             const std::vector<NpuEventId>& dependencies = {});
    NpuEventId waitRequests(std::uint64_t op_desc,
                            const std::vector<std::uint64_t>& wait_request_ids,
                            const std::vector<NpuEventId>& dependencies = {});
    NpuEventId barrier(std::uint64_t op_desc,
                       const std::vector<NpuEventId>& dependencies = {});

    const std::vector<NpuProgramEvent>& events() const;
    void clear();

private:
    NpuEventId append(NpuProgramEventKind kind,
                      std::uint64_t op_desc,
                      int mac_id,
                      std::uint64_t address,
                      std::uint64_t bytes,
                      std::uint64_t ops,
                      const std::vector<std::uint64_t>& wait_request_ids,
                      const std::vector<NpuEventId>& dependencies);

    NpuEventId next_id_ = 1;
    std::vector<NpuProgramEvent> events_;
};

struct NpuProgramScheduleEntry {
    NpuProgramEvent event;
    std::uint64_t ready_cycle = 0;
    std::uint64_t issue_cycle = 0;
    std::uint64_t start_cycle = 0;
    std::uint64_t complete_cycle = 0;
};

struct NpuProgramScheduleResult {
    std::uint64_t finish_cycle = 0;
    std::uint64_t dma_finish_cycle = 0;
    std::uint64_t mac_finish_cycle = 0;
    std::uint64_t vector_finish_cycle = 0;
    std::uint64_t reduce_finish_cycle = 0;
    std::uint64_t external_finish_cycle = 0;
    std::uint64_t overall_finish_cycle = 0;
    // Sum of one offline PopNet intra-NPU delay injection per operator
    // descriptor.  This is a report value; concurrent MAC events belonging
    // to the same descriptor share the same data-ready gate.
    std::uint64_t injected_intra_cycles = 0;
    std::map<NpuEventId, std::uint64_t> event_complete_cycles;
    std::vector<NpuProgramScheduleEntry> entries;
};

struct IntraDelayProfile {
    bool loaded = false;
    std::uint64_t total_dst_delay = 0;
    std::uint64_t total_src_delay = 0;
    std::uint64_t packet_count = 0;
    std::map<std::uint64_t, std::uint64_t> task_dst_delay;
    std::map<std::uint64_t, std::uint64_t> task_src_delay;
    std::map<int, std::uint64_t> mac_dst_delay;
    std::map<int, std::uint64_t> mac_src_delay;
};

NPUConfig loadConfig(const std::string& path);
TopologyInfo describeTopology(const NPUConfig& config);
IntraDelayProfile loadIntraDelayProfile(const std::string& path);
std::uint64_t loadIntraDelayCycles(const std::string& path);
Model parseOnnxModel(const std::vector<char>& bytes);
// Execute supported ONNX operators on host-resident float tensors without
// emitting a bench, performing DMA, or advancing simulated cycles.  Inputs
// map in graph-input order after initializers are excluded.  A one-element
// input is broadcast to the corresponding static graph-input shape, which is
// useful for a scalar start/value protocol in a workload template.
FunctionalOnnxResult runOnnxFunctionally(
    const std::vector<char>& model_bytes,
    const std::vector<Tensor>& external_inputs,
    const FunctionalOnnxExecutionOptions& options = FunctionalOnnxExecutionOptions{});
RunResult runModel(const std::vector<char>& model_bytes,
                   const std::vector<std::int64_t>& input0,
                   const std::vector<std::int64_t>& input1,
                   const NPUConfig& config,
                   const std::string& bench_path,
                   const std::string& delay_profile_path,
                   bool estimate_only);
RunResult runMatMulI64(const std::vector<std::int64_t>& input0,
                       const std::vector<std::int64_t>& input1,
                       std::int64_t rows_a,
                       std::int64_t cols_a,
                       std::int64_t cols_b,
                       const NPUConfig& config,
                       const std::string& bench_path,
                       const std::string& delay_profile_path,
                       bool estimate_only,
                       const std::string& task_name = "direct_matmul");
// Timing is datatype-independent: byte widths come from NPUConfig.  This is
// the canonical tiled MatMul planner used by ONNX and direct callers alike.
std::vector<NpuTileEvent> planMatMulTiles(std::int64_t rows_a,
                                          std::int64_t cols_a,
                                          std::int64_t cols_b,
                                          const NPUConfig& config);
// Compatibility entry point for older direct-int64 benchmark code.  It is an
// alias in behaviour, not a separate int64 timing model.
std::vector<MatMulTileEvent> planMatMulI64Tiles(std::int64_t rows_a,
                                                std::int64_t cols_a,
                                                std::int64_t cols_b,
                                                const NPUConfig& config);
NpuTileScheduleResult scheduleNpuTileEvents(
    const std::vector<NpuTileEvent>& events,
    const NPUConfig& config,
    std::uint64_t initial_cycle,
    std::uint64_t injected_intra_cycles,
    const NpuMemoryTransferCallback& transfer_callback = NpuMemoryTransferCallback{});

// Emits the offline, controller<->MAC traffic of a generic primitive program
// in PopNet bench format.  It is deliberately separate from chiplet DRAM
// traffic: this file is consumed only by the NPU-intra PopNet calibration.
// Each non-zero op_desc becomes one profile TASK, so the returned profile can
// be injected into the same event program during the later online phase.
void writeNpuProgramIntraBench(const std::vector<NpuProgramEvent>& events,
                               const NPUConfig& config,
                               const std::string& bench_path);

// Schedules a recorder-produced program in append order.  Dependencies must
// only target earlier events, making dataflow explicit and deterministic.  A
// supplied memory callback returns an absolute completion cycle (e.g. from a
// DRAM chiplet); without one DMA uses the configured DDR-bandwidth estimate.
// When intra_delay_profile is supplied, one task-level delay is applied before
// the first compute event of each op_desc.  All MACs in that task share the
// gate, so this does not multiply one network delay by MAC count.
NpuProgramScheduleResult scheduleNpuProgramEvents(
    const std::vector<NpuProgramEvent>& events,
    const NPUConfig& config,
    std::uint64_t initial_cycle,
    const NpuMemoryTransferCallback& transfer_callback = NpuMemoryTransferCallback{},
    const IntraDelayProfile* intra_delay_profile = nullptr,
    const NpuRequestCompletionResolver& request_completion_resolver =
        NpuRequestCompletionResolver{});
void writeJsonReport(const std::string& path, const RunResult& result);

}  // namespace NPUSim

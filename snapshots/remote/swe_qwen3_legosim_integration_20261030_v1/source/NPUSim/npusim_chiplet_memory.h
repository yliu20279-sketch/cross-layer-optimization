#pragma once

#include "npusim_runtime.h"

#include <cstddef>
#include <cstdint>
#include <functional>
#include <map>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

namespace NPUSim {

// All benchmark-specific choices belong here, instead of being copied into
// every workload.  A workload normally needs only self coordinates, a report
// directory, and the timing trace emitted by the external LPDDR5 chiplet.
struct ChipletMemoryClientOptions {
    int self_x = 0;
    int self_y = 0;
    std::string transaction_trace_path;
    std::string log_prefix = "[NPUSIM][DRAM]";

    // Used only by makeTraceDmaCallback() when a generic event did not carry
    // an address.  Normal workloads should set event.address explicitly.
    // Zero selects the upper half of configured DRAM as a trace-only region.
    std::uint64_t trace_base_address = 0;
};

// A data binding makes a scheduled DMA carry the same bytes used by the
// functional ONNX path.  A load fills load_destination from the DRAM server;
// a store gets its payload lazily when the scheduler reaches that event.  The
// lazy store is important: its host calculation may finish early or late, but
// the write is still issued at the modeled DMA cycle.
struct ChipletDmaPayloadBinding {
    // Program-event id.  Zero keeps the legacy address/byte-only match, while
    // a non-zero value makes bindings unambiguous when two tensors happen to
    // have the same address and size.
    std::uint64_t logical_id = 0;
    std::uint64_t address = 0;
    std::uint64_t bytes = 0;
    std::vector<std::uint8_t>* load_destination = nullptr;
    std::function<void()> after_load;
    std::function<const std::vector<std::uint8_t>&()> store_source;
    std::string label;
};

// A functional C++ workload may already materialise some input/output bytes
// through store()/load().  Credits prevent that physical traffic from being
// emitted again by a subsequent timing-only tile/event schedule.  New ONNX
// wrappers should prefer payload_bindings, which avoid duplicate traffic and
// make a scheduled DMA move the real functional bytes.
struct ChipletDmaCallbackOptions {
    std::uint64_t read_trace_address = 0;
    std::uint64_t write_trace_address = 0;
    std::uint64_t read_byte_credit = 0;
    std::uint64_t write_byte_credit = 0;
    // Default decoupled mode: DMA requests are still sent to the external
    // LPDDR5 module, but the scheduler only sees the NPU-side DDR-port
    // completion.  Set this true only when modeling a blocking functional
    // path that must gate NPU compute on external DRAM response time.
    bool gate_on_external_completion = true;
    std::vector<ChipletDmaPayloadBinding> payload_bindings;
};

// One explicit NPU<->DRAM completion record.  This is emitted after the
// request has been serviced by the external LPDDR5 chiplet and the return
// synchronization has been observed by NPUSim.
struct ChipletDramCompletionRecord {
    std::uint64_t request_id = 0;
    bool is_write = false;
    std::uint64_t address = 0;
    std::uint64_t bytes = 0;
    std::uint64_t issue_cycle = 0;
    std::uint64_t complete_cycle = 0;
    std::uint64_t external_elapsed_cycles = 0;
    std::string label;
};

struct ChipletDramPendingRequest {
    std::uint64_t request_id = 0;
    bool is_write = false;
    std::uint64_t address = 0;
    std::size_t bytes = 0;
    std::uint64_t issue_cycle = 0;
    std::string label;
};

// Reusable LEGOSim client for an external DRAM chiplet.  It owns the stable
// request-id stream, the transaction CSV, and the InterChiplet request/response
// protocol.  It does not own tensor semantics or NPU scheduling: workloads
// keep those in their functional code and use makeTraceDmaCallback() with
// scheduleNpu*Events().
class ChipletMemoryClient {
  public:
    ChipletMemoryClient(const NPUConfig& config,
                        const ChipletMemoryClientOptions& options,
                        unsigned long long& chip_cycle);
    ~ChipletMemoryClient();

    ChipletMemoryClient(const ChipletMemoryClient&) = delete;
    ChipletMemoryClient& operator=(const ChipletMemoryClient&) = delete;

    bool enabled() const;
    // Functional transfers: payload bytes are materialised through the shared
    // DRAM chiplet.  Use them for inputs/outputs whose values are needed by a
    // C++ reference model.
    void store(std::uint64_t address,
               const void* data,
               std::size_t bytes,
               const std::string& label);
    void load(std::uint64_t address,
              void* data,
              std::size_t bytes,
              const std::string& label);

    // Timing-only traffic uses a reusable burst buffer and never allocates a
    // tensor-sized host buffer.
    void storeTrace(std::uint64_t address, std::size_t bytes, const std::string& label);
    void loadTrace(std::uint64_t address, std::size_t bytes, const std::string& label);

    const std::vector<ChipletDramCompletionRecord>& completionRecords() const;
    std::optional<ChipletDramCompletionRecord> findCompletion(std::uint64_t request_id) const;
    std::size_t pendingRequestCount() const;

    // A drop-in callback for scheduleNpuTileEvents() or
    // scheduleNpuProgramEvents().  The runtime supplies the request's legal
    // issue cycle; this method emits external LPDDR5 traffic and, by default,
    // returns only the NPU-side DDR-port completion cycle to keep on-chip NPU
    // timing separate from DRAM service time.
    NpuMemoryTransferCallback makeTraceDmaCallback(
        const ChipletDmaCallbackOptions& options = ChipletDmaCallbackOptions{});

    // Send a shutdown marker once this NPU client has completed.  The shared
    // DRAM server exits after receiving one marker from every configured NPU.
    void shutdown();

  private:
    void transferChunks(bool is_write,
                        std::uint64_t address,
                        std::uint8_t* data,
                        std::size_t bytes,
                        const std::string& label);
    void transferTrace(bool is_write,
                       std::uint64_t address,
                       std::size_t bytes,
                       const std::string& label);
    void transferOne(bool is_write,
                     std::uint64_t address,
                     std::uint8_t* data,
                     std::size_t bytes,
                     const std::string& label);
    ChipletDramPendingRequest issueRequest(bool is_write,
                                           std::uint64_t address,
                                           std::size_t bytes,
                                           const std::string& label);
    ChipletDramCompletionRecord completeRequest(const ChipletDramPendingRequest& pending,
                                                int transport_bytes);
    std::uint64_t nextRequestId();
    bool enabled_ = false;
    bool stopped_ = false;
    NPUConfig config_;
    int dram_x_ = -1;
    int dram_y_ = -1;
    std::uint64_t burst_bytes_ = 1;
    int self_x_ = 0;
    int self_y_ = 0;
    unsigned long long& chip_cycle_;
    std::uint64_t next_request_sequence_ = 1;
    std::uint64_t next_trace_address_ = 0;
    std::string log_prefix_;
    std::vector<std::uint8_t> trace_scratch_;
    std::vector<ChipletDramCompletionRecord> completion_records_;
    std::unordered_map<std::uint64_t, ChipletDramPendingRequest> pending_requests_;
    class Impl;
    Impl* impl_ = nullptr;
};

}  // namespace NPUSim

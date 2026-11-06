#include "npusim_chiplet_memory.h"

#include "../Ramulator2-Chiplet/dram_chiplet_protocol.h"
#include "../interchiplet/includes/pipe_comm.h"
#include "../interchiplet/includes/sync_protocol.h"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <utility>

namespace NPUSim {

namespace {

int checkedTransportSize(std::size_t bytes) {
    if (bytes == 0 || bytes > static_cast<std::size_t>(std::numeric_limits<int>::max())) {
        throw std::runtime_error("invalid DRAM chiplet transfer size");
    }
    return static_cast<int>(bytes);
}

std::string requestLabel(const NpuMemoryRequest& request) {
    return "op_" + std::to_string(request.op_desc) +
           "_tile_" + std::to_string(request.tile_id) +
           (request.is_write ? "_write" : "_read");
}

std::uint64_t alignUp(std::uint64_t value, std::uint64_t alignment) {
    alignment = std::max<std::uint64_t>(1, alignment);
    if (value > std::numeric_limits<std::uint64_t>::max() - (alignment - 1)) {
        throw std::runtime_error("DRAM trace address overflow");
    }
    return ((value + alignment - 1) / alignment) * alignment;
}

}  // namespace

class ChipletMemoryClient::Impl {
  public:
    InterChiplet::PipeComm pipe_comm;
    std::ofstream transaction_trace;
};

ChipletMemoryClient::ChipletMemoryClient(const NPUConfig& config,
                                         const ChipletMemoryClientOptions& options,
                                         unsigned long long& chip_cycle)
    : enabled_(config.external_memory_enable && config.external_memory_model == "chiplet"),
      config_(config),
      dram_x_(config.dram_chiplet_x),
      dram_y_(config.dram_chiplet_y),
      burst_bytes_(std::max<std::uint64_t>(1, config.dram_chiplet_burst_bytes)),
      self_x_(options.self_x),
      self_y_(options.self_y),
      chip_cycle_(chip_cycle),
      next_trace_address_(options.trace_base_address == 0
                              ? alignUp(config.dram_size_bytes / 2, burst_bytes_)
                              : alignUp(options.trace_base_address, burst_bytes_)),
      log_prefix_(options.log_prefix.empty() ? "[NPUSIM][DRAM]" : options.log_prefix),
      impl_(new Impl()) {
    if (enabled_ && (dram_x_ < 0 || dram_y_ < 0)) {
        throw std::runtime_error("external_memory.model=chiplet requires external_memory.chiplet.x/y");
    }
    if (enabled_ && (self_x_ < 0 || self_x_ > 15 || self_y_ < 0 || self_y_ > 15)) {
        throw std::runtime_error("NPU coordinate is outside request-id encoding range");
    }
    if (burst_bytes_ > static_cast<std::uint64_t>(std::numeric_limits<int>::max()) ||
        burst_bytes_ > static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max())) {
        throw std::runtime_error("DRAM chiplet burst size exceeds host transport limits");
    }
    trace_scratch_.resize(static_cast<std::size_t>(burst_bytes_), 0);
    if (!options.transaction_trace_path.empty()) {
        const std::filesystem::path trace_path(options.transaction_trace_path);
        if (!trace_path.parent_path().empty()) {
            std::filesystem::create_directories(trace_path.parent_path());
        }
        impl_->transaction_trace.open(options.transaction_trace_path, std::ios::out | std::ios::trunc);
        if (!impl_->transaction_trace.is_open()) {
            throw std::runtime_error("cannot open NPU DRAM transaction trace: " +
                                     options.transaction_trace_path);
        }
        impl_->transaction_trace << "request_id,operation,label,address,bytes,issue_cycle,"
                                  "npu_dma_cycles,external_elapsed_cycles,"
                                  "phase1_elapsed_cycles,total_elapsed_cycles\n";
    }
}

ChipletMemoryClient::~ChipletMemoryClient() {
    delete impl_;
}

bool ChipletMemoryClient::enabled() const {
    return enabled_;
}

void ChipletMemoryClient::store(std::uint64_t address,
                                const void* data,
                                std::size_t bytes,
                                const std::string& label) {
    transferChunks(true, address, const_cast<std::uint8_t*>(static_cast<const std::uint8_t*>(data)),
                   bytes, label);
}

void ChipletMemoryClient::load(std::uint64_t address,
                               void* data,
                               std::size_t bytes,
                               const std::string& label) {
    transferChunks(false, address, static_cast<std::uint8_t*>(data), bytes, label);
}

void ChipletMemoryClient::storeTrace(std::uint64_t address,
                                     std::size_t bytes,
                                     const std::string& label) {
    transferTrace(true, address, bytes, label);
}

void ChipletMemoryClient::loadTrace(std::uint64_t address,
                                    std::size_t bytes,
                                    const std::string& label) {
    transferTrace(false, address, bytes, label);
}

const std::vector<ChipletDramCompletionRecord>& ChipletMemoryClient::completionRecords() const {
    return completion_records_;
}

std::optional<ChipletDramCompletionRecord> ChipletMemoryClient::findCompletion(
    std::uint64_t request_id) const {
    for (const ChipletDramCompletionRecord& record : completion_records_) {
        if (record.request_id == request_id) {
            return record;
        }
    }
    return std::nullopt;
}

std::size_t ChipletMemoryClient::pendingRequestCount() const {
    return pending_requests_.size();
}

NpuMemoryTransferCallback ChipletMemoryClient::makeTraceDmaCallback(
    const ChipletDmaCallbackOptions& options) {
    const std::uint64_t default_base = next_trace_address_;
    std::uint64_t read_cursor = options.read_trace_address == 0
        ? default_base : alignUp(options.read_trace_address, burst_bytes_);
    std::uint64_t write_cursor = options.write_trace_address == 0
        ? default_base : alignUp(options.write_trace_address, burst_bytes_);
    std::uint64_t read_credit = options.read_byte_credit;
    std::uint64_t write_credit = options.write_byte_credit;
    const std::vector<ChipletDmaPayloadBinding> payload_bindings = options.payload_bindings;
    const bool gate_on_external_completion = options.gate_on_external_completion;
    return [this, read_cursor, write_cursor, read_credit, write_credit, payload_bindings,
            gate_on_external_completion](
               const NpuMemoryRequest& request, std::uint64_t issue_cycle) mutable {
        if (!enabled_) {
            return issue_cycle;
        }
        const std::uint64_t npu_port_bandwidth =
            std::max<std::uint64_t>(1, config_.ddr_bandwidth_bytes_per_cycle);
        const std::uint64_t npu_port_complete = issue_cycle +
            ((request.bytes + npu_port_bandwidth - 1) / npu_port_bandwidth);
        chip_cycle_ = std::max<unsigned long long>(chip_cycle_, issue_cycle);
        for (const ChipletDmaPayloadBinding& binding : payload_bindings) {
            if ((binding.logical_id != 0 && binding.logical_id != request.logical_id) ||
                binding.address != request.address || binding.bytes != request.bytes) {
                continue;
            }
            const std::string label = binding.label.empty() ? requestLabel(request) : binding.label;
            if (request.is_write) {
                if (!binding.store_source) {
                    throw std::runtime_error("scheduled DRAM store has no functional payload source: " + label);
                }
                const std::vector<std::uint8_t>& payload = binding.store_source();
                if (payload.size() != static_cast<std::size_t>(binding.bytes)) {
                    throw std::runtime_error("scheduled DRAM store payload size differs from ONNX DMA bytes: " + label);
                }
                store(binding.address, payload.data(), payload.size(), label);
            } else {
                if (binding.load_destination == nullptr) {
                    throw std::runtime_error("scheduled DRAM load has no functional destination: " + label);
                }
                binding.load_destination->assign(static_cast<std::size_t>(binding.bytes), 0);
                load(binding.address, binding.load_destination->data(),
                     binding.load_destination->size(), label);
                if (binding.after_load) {
                    binding.after_load();
                }
            }
            return gate_on_external_completion
                ? static_cast<std::uint64_t>(chip_cycle_)
                : npu_port_complete;
        }
        std::uint64_t trace_bytes = request.bytes;
        std::uint64_t& credit = request.is_write ? write_credit : read_credit;
        const std::uint64_t credited = std::min(trace_bytes, credit);
        trace_bytes -= credited;
        credit -= credited;
        if (trace_bytes != 0) {
            std::uint64_t address = 0;
            if (request.address != 0) {
                if (request.address > std::numeric_limits<std::uint64_t>::max() - credited) {
                    throw std::runtime_error("DRAM event address overflow");
                }
                address = request.address + credited;
            } else {
                std::uint64_t& cursor = request.is_write ? write_cursor : read_cursor;
                address = alignUp(cursor, burst_bytes_);
                if (address > std::numeric_limits<std::uint64_t>::max() - trace_bytes) {
                    throw std::runtime_error("DRAM trace address overflow");
                }
                cursor = alignUp(address + trace_bytes, burst_bytes_);
            }
            transferTrace(request.is_write, address, static_cast<std::size_t>(trace_bytes),
                          requestLabel(request));
        }
        return gate_on_external_completion
            ? static_cast<std::uint64_t>(chip_cycle_)
            : npu_port_complete;
    };
}

void ChipletMemoryClient::shutdown() {
    if (!enabled_ || stopped_) {
        return;
    }
    DramChiplet::Request request{};
    request.operation = static_cast<std::uint64_t>(DramChiplet::Operation::kShutdown);
    request.request_id = nextRequestId();
    const unsigned long long begin = chip_cycle_;
    InterChiplet::launchSync(self_x_, self_y_, dram_x_, dram_y_);
    const std::string command_pipe = InterChiplet::sendSync(self_x_, self_y_, dram_x_, dram_y_);
    if (impl_->pipe_comm.write_data(command_pipe.c_str(), &request, sizeof(request)) !=
        static_cast<int>(sizeof(request))) {
        throw std::runtime_error("short DRAM chiplet shutdown request write");
    }
    chip_cycle_ = InterChiplet::writeSync(chip_cycle_, self_x_, self_y_, dram_x_, dram_y_,
                                           static_cast<int>(sizeof(request)),
                                           static_cast<long>(request.request_id));
    stopped_ = true;
    std::cout << log_prefix_ << " shutdown id=" << request.request_id
              << " cycles=" << (chip_cycle_ - begin) << std::endl;
}

void ChipletMemoryClient::transferChunks(bool is_write,
                                         std::uint64_t address,
                                         std::uint8_t* data,
                                         std::size_t bytes,
                                         const std::string& label) {
    if (!enabled_) {
        return;
    }
    if (stopped_) {
        throw std::runtime_error("attempted a DRAM access after shutdown");
    }
    if (data == nullptr || bytes == 0) {
        throw std::runtime_error("invalid zero-sized DRAM access");
    }
    for (std::size_t offset = 0; offset < bytes;) {
        const std::size_t chunk = static_cast<std::size_t>(std::min<std::uint64_t>(
            burst_bytes_, static_cast<std::uint64_t>(bytes - offset)));
        transferOne(is_write, address + offset, data + offset, chunk, label);
        offset += chunk;
    }
}

void ChipletMemoryClient::transferTrace(bool is_write,
                                        std::uint64_t address,
                                        std::size_t bytes,
                                        const std::string& label) {
    if (!enabled_ || bytes == 0) {
        return;
    }
    for (std::size_t offset = 0; offset < bytes;) {
        const std::size_t chunk = std::min(trace_scratch_.size(), bytes - offset);
        transferOne(is_write, address + offset, trace_scratch_.data(), chunk, label);
        offset += chunk;
    }
}

void ChipletMemoryClient::transferOne(bool is_write,
                                      std::uint64_t address,
                                      std::uint8_t* data,
                                      std::size_t bytes,
                                      const std::string& label) {
    if (address > config_.dram_size_bytes || bytes > config_.dram_size_bytes - address) {
        throw std::runtime_error("DRAM chiplet access is outside configured DRAM size");
    }
    const ChipletDramPendingRequest pending = issueRequest(is_write, address, bytes, label);
    const int transport_bytes = checkedTransportSize(bytes);

    if (is_write) {
        const std::string data_pipe = InterChiplet::sendSync(self_x_, self_y_, dram_x_, dram_y_);
        if (impl_->pipe_comm.write_data(data_pipe.c_str(), data, transport_bytes) != transport_bytes) {
            throw std::runtime_error("short DRAM chiplet store payload write");
        }
        chip_cycle_ = InterChiplet::writeSync(chip_cycle_, self_x_, self_y_, dram_x_, dram_y_,
                                               transport_bytes,
                                               static_cast<long>(pending.request_id));
    } else {
        const std::string data_pipe = InterChiplet::receiveSync(dram_x_, dram_y_, self_x_, self_y_);
        if (impl_->pipe_comm.read_data(data_pipe.c_str(), data, transport_bytes) != transport_bytes) {
            throw std::runtime_error("short DRAM chiplet load payload read");
        }
        chip_cycle_ = InterChiplet::readSync(chip_cycle_, dram_x_, dram_y_, self_x_, self_y_,
                                              transport_bytes,
                                              static_cast<long>(pending.request_id));
    }

    const ChipletDramCompletionRecord completion = completeRequest(pending, transport_bytes);
    if (impl_->transaction_trace.is_open()) {
        impl_->transaction_trace << completion.request_id << ','
                                 << (is_write ? "STORE" : "LOAD") << ','
                                 << label << ',' << address << ',' << bytes << ','
                                 << completion.issue_cycle << ','
                                 << checkedTransportSize(bytes) << ','
                                 << completion.external_elapsed_cycles << ','
                                 << completion.external_elapsed_cycles << ','
                                 << completion.external_elapsed_cycles << '\n';
        impl_->transaction_trace.flush();
    }
    std::cout << log_prefix_ << ' ' << (is_write ? "store" : "load")
              << " id=" << completion.request_id << " label=" << label
              << " addr=" << address << " bytes=" << bytes
              << " npu_dma_cycles=" << checkedTransportSize(bytes)
              << " external_cycles=" << completion.external_elapsed_cycles << std::endl;
}

ChipletDramPendingRequest ChipletMemoryClient::issueRequest(bool is_write,
                                                            std::uint64_t address,
                                                            std::size_t bytes,
                                                            const std::string& label) {
    const unsigned long long begin = chip_cycle_;
    DramChiplet::Request request{};
    request.operation = static_cast<std::uint64_t>(
        is_write ? DramChiplet::Operation::kStore : DramChiplet::Operation::kLoad);
    request.bytes = bytes;
    request.address = address;
    request.request_id = nextRequestId();

    InterChiplet::launchSync(self_x_, self_y_, dram_x_, dram_y_);
    const std::string command_pipe = InterChiplet::sendSync(self_x_, self_y_, dram_x_, dram_y_);
    if (impl_->pipe_comm.write_data(command_pipe.c_str(), &request, sizeof(request)) !=
        static_cast<int>(sizeof(request))) {
        throw std::runtime_error("short DRAM chiplet request write");
    }
    chip_cycle_ = InterChiplet::writeSync(chip_cycle_, self_x_, self_y_, dram_x_, dram_y_,
                                           static_cast<int>(sizeof(request)),
                                           static_cast<long>(request.request_id));

    ChipletDramPendingRequest pending;
    pending.request_id = request.request_id;
    pending.is_write = is_write;
    pending.address = address;
    pending.bytes = bytes;
    pending.issue_cycle = begin;
    pending.label = label;
    pending_requests_.emplace(pending.request_id, pending);
    return pending;
}

ChipletDramCompletionRecord ChipletMemoryClient::completeRequest(
    const ChipletDramPendingRequest& pending,
    int transport_bytes) {
    if (pending.is_write) {
        const std::string reply_pipe = InterChiplet::receiveSync(dram_x_, dram_y_, self_x_, self_y_);
        DramChiplet::Reply reply{};
        if (impl_->pipe_comm.read_data(reply_pipe.c_str(), &reply, sizeof(reply)) !=
            static_cast<int>(sizeof(reply))) {
            throw std::runtime_error("short DRAM chiplet store reply read");
        }
        chip_cycle_ = InterChiplet::readSync(chip_cycle_, dram_x_, dram_y_, self_x_, self_y_,
                                              static_cast<int>(sizeof(reply)),
                                              static_cast<long>(pending.request_id));
        if (reply.request_id != pending.request_id || reply.status != 0) {
            throw std::runtime_error("DRAM chiplet rejected store request");
        }
    }

    const std::uint64_t external_elapsed = chip_cycle_ - pending.issue_cycle;
    const ChipletDramCompletionRecord completion{
        pending.request_id,
        pending.is_write,
        pending.address,
        static_cast<std::uint64_t>(transport_bytes),
        pending.issue_cycle,
        chip_cycle_,
        external_elapsed,
        pending.label,
    };
    completion_records_.push_back(completion);
    pending_requests_.erase(pending.request_id);
    return completion;
}

std::uint64_t ChipletMemoryClient::nextRequestId() {
    constexpr std::uint64_t kSequenceLimit = (1ULL << 20) - 1;
    if (next_request_sequence_ == 0 || next_request_sequence_ > kSequenceLimit) {
        throw std::runtime_error("NPU DRAM request-id sequence overflow");
    }
    const std::uint64_t request_id = DramChiplet::kNpuRequestIdMagic |
        (static_cast<std::uint64_t>(static_cast<unsigned int>(self_x_)) << 44) |
        (static_cast<std::uint64_t>(static_cast<unsigned int>(self_y_)) << 40) |
        (next_request_sequence_ << 20);
    ++next_request_sequence_;
    return request_id;
}

}  // namespace NPUSim

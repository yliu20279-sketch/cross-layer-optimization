#include <algorithm>
#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

#include "cpu_npu_onnx_protocol.h"
#include "dram_chiplet_protocol.h"
#include "npusim_tensor_codec.h"
#include "pipe_comm.h"
#include "sync_protocol.h"

namespace {

// 三个芯粒的固定坐标必须与 cpu_onnx_chiplet.yml、npu_chiplet_config.json
// 以及 cpu_npu_dram_3.gv 一致。CPU 只发送控制描述符，不直接传递大 tensor。
constexpr int kCpuX = 0;
constexpr int kCpuY = 0;
constexpr int kNpuX = 1;
constexpr int kNpuY = 0;
constexpr int kDramX = 2;
constexpr int kDramY = 0;
constexpr std::size_t kMaxTransferBytes = 4096;
constexpr std::uint64_t kHiddenStateDramAddress = 0;

InterChiplet::PipeComm g_pipe_comm;

std::int64_t checkedI64(std::size_t value, const char* field) {
    if (value > static_cast<std::size_t>(std::numeric_limits<std::int64_t>::max())) {
        throw std::runtime_error(std::string("CPU tensor ") + field + " exceeds int64 protocol range");
    }
    return static_cast<std::int64_t>(value);
}

template <typename T>
void sendToNpu(const T& payload, unsigned long long& cycle) {
    // 控制包路径：CPU -> NPU。writeSync 既推进 CPU 本地时间，也记录片间通信。
    const std::string pipe = InterChiplet::sendSync(kCpuX, kCpuY, kNpuX, kNpuY);
    if (g_pipe_comm.write_data(pipe.c_str(), const_cast<T*>(&payload), sizeof(T)) !=
        static_cast<int>(sizeof(T))) {
        throw std::runtime_error("CPU failed to send NPU metadata");
    }
    cycle = InterChiplet::writeSync(cycle, kCpuX, kCpuY, kNpuX, kNpuY, sizeof(T), 0);
}

void sendShapeToNpu(const std::vector<std::int64_t>& shape, unsigned long long& cycle) {
    // shape 是控制元数据；过大时切块，避免单次 PipeComm 传输超过上限。
    const auto* cursor = reinterpret_cast<const std::uint8_t*>(shape.data());
    const std::size_t bytes = shape.size() * sizeof(shape.front());
    for (std::size_t offset = 0; offset < bytes;) {
        const std::size_t chunk = std::min(kMaxTransferBytes, bytes - offset);
        const std::string pipe = InterChiplet::sendSync(kCpuX, kCpuY, kNpuX, kNpuY);
        if (g_pipe_comm.write_data(pipe.c_str(), const_cast<std::uint8_t*>(cursor + offset),
                                   static_cast<int>(chunk)) != static_cast<int>(chunk)) {
            throw std::runtime_error("CPU failed to send NPU tensor shape");
        }
        cycle = InterChiplet::writeSync(cycle, kCpuX, kCpuY, kNpuX, kNpuY,
                                        static_cast<int>(chunk), 0);
        offset += chunk;
    }
}

template <typename T>
void receiveFromNpu(T& payload, unsigned long long& cycle) {
    // 控制包路径：NPU -> CPU，例如完成状态与输出 DRAM 描述符。
    const std::string pipe = InterChiplet::receiveSync(kNpuX, kNpuY, kCpuX, kCpuY);
    if (g_pipe_comm.read_data(pipe.c_str(), &payload, sizeof(T)) != static_cast<int>(sizeof(T))) {
        throw std::runtime_error("CPU failed to receive NPU metadata");
    }
    cycle = InterChiplet::readSync(cycle, kNpuX, kNpuY, kCpuX, kCpuY, sizeof(T), 0);
}

void receiveShapeFromNpu(std::vector<std::int64_t>& shape, unsigned long long& cycle) {
    auto* cursor = reinterpret_cast<std::uint8_t*>(shape.data());
    const std::size_t bytes = shape.size() * sizeof(shape.front());
    for (std::size_t offset = 0; offset < bytes;) {
        const std::size_t chunk = std::min(kMaxTransferBytes, bytes - offset);
        const std::string pipe = InterChiplet::receiveSync(kNpuX, kNpuY, kCpuX, kCpuY);
        if (g_pipe_comm.read_data(pipe.c_str(), cursor + offset, static_cast<int>(chunk)) !=
            static_cast<int>(chunk)) {
            throw std::runtime_error("CPU failed to receive NPU output shape");
        }
        cycle = InterChiplet::readSync(cycle, kNpuX, kNpuY, kCpuX, kCpuY,
                                       static_cast<int>(chunk), 0);
        offset += chunk;
    }
}

std::uint64_t cpuRequestId(std::uint64_t sequence) {
    return 0x4350550000000000ULL + sequence;
}

void storeBytesToDram(std::uint64_t address,
                      const std::vector<std::uint8_t>& payload,
                      unsigned long long& cycle) {
    // 功能数据路径：CPU 将真实输入字节写入共享 DRAM。每个 chunk 都是独立的
    // DRAM 请求，因此会出现在全局 bench.txt 与 DRAM timing trace 中。
    std::uint64_t sequence = 1;
    for (std::size_t offset = 0; offset < payload.size();) {
        const std::size_t chunk = std::min(kMaxTransferBytes, payload.size() - offset);
        DramChiplet::Request request{};
        request.operation = static_cast<std::uint64_t>(DramChiplet::Operation::kStore);
        request.bytes = chunk;
        request.address = address + offset;
        request.request_id = cpuRequestId(sequence++);
        InterChiplet::launchSync(kCpuX, kCpuY, kDramX, kDramY);
        const std::string command_pipe = InterChiplet::sendSync(kCpuX, kCpuY, kDramX, kDramY);
        if (g_pipe_comm.write_data(command_pipe.c_str(), &request, sizeof(request)) !=
            static_cast<int>(sizeof(request))) {
            throw std::runtime_error("CPU failed to send DRAM store request");
        }
        cycle = InterChiplet::writeSync(cycle, kCpuX, kCpuY, kDramX, kDramY,
                                        sizeof(request), static_cast<long>(request.request_id));
        const std::string data_pipe = InterChiplet::sendSync(kCpuX, kCpuY, kDramX, kDramY);
        if (g_pipe_comm.write_data(data_pipe.c_str(), const_cast<std::uint8_t*>(payload.data() + offset),
                                   static_cast<int>(chunk)) != static_cast<int>(chunk)) {
            throw std::runtime_error("CPU failed to send DRAM store payload");
        }
        cycle = InterChiplet::writeSync(cycle, kCpuX, kCpuY, kDramX, kDramY,
                                        static_cast<int>(chunk), static_cast<long>(request.request_id));
        DramChiplet::Reply reply{};
        const std::string reply_pipe = InterChiplet::receiveSync(kDramX, kDramY, kCpuX, kCpuY);
        if (g_pipe_comm.read_data(reply_pipe.c_str(), &reply, sizeof(reply)) != static_cast<int>(sizeof(reply)) ||
            reply.request_id != request.request_id || reply.status != 0) {
            throw std::runtime_error("CPU DRAM store failed");
        }
        cycle = InterChiplet::readSync(cycle, kDramX, kDramY, kCpuX, kCpuY,
                                       sizeof(reply), static_cast<long>(request.request_id));
        offset += chunk;
    }
}

std::vector<std::uint8_t> loadBytesFromDram(std::uint64_t address,
                                             std::size_t bytes,
                                             unsigned long long& cycle) {
    // 功能数据路径：CPU 从共享 DRAM 读取 NPU 已写回的真实输出字节。
    std::vector<std::uint8_t> result(bytes);
    std::uint64_t sequence = 0x100000;
    for (std::size_t offset = 0; offset < result.size();) {
        const std::size_t chunk = std::min(kMaxTransferBytes, result.size() - offset);
        DramChiplet::Request request{};
        request.operation = static_cast<std::uint64_t>(DramChiplet::Operation::kLoad);
        request.bytes = chunk;
        request.address = address + offset;
        request.request_id = cpuRequestId(sequence++);
        InterChiplet::launchSync(kCpuX, kCpuY, kDramX, kDramY);
        const std::string command_pipe = InterChiplet::sendSync(kCpuX, kCpuY, kDramX, kDramY);
        if (g_pipe_comm.write_data(command_pipe.c_str(), &request, sizeof(request)) !=
            static_cast<int>(sizeof(request))) {
            throw std::runtime_error("CPU failed to send DRAM load request");
        }
        cycle = InterChiplet::writeSync(cycle, kCpuX, kCpuY, kDramX, kDramY,
                                        sizeof(request), static_cast<long>(request.request_id));
        const std::string data_pipe = InterChiplet::receiveSync(kDramX, kDramY, kCpuX, kCpuY);
        if (g_pipe_comm.read_data(data_pipe.c_str(), result.data() + offset, static_cast<int>(chunk)) !=
            static_cast<int>(chunk)) {
            throw std::runtime_error("CPU failed to receive DRAM load payload");
        }
        cycle = InterChiplet::readSync(cycle, kDramX, kDramY, kCpuX, kCpuY,
                                       static_cast<int>(chunk), static_cast<long>(request.request_id));
        offset += chunk;
    }
    return result;
}

std::size_t checkedElementCount(const std::vector<std::int64_t>& shape) {
    std::size_t elements = 1;
    for (const std::int64_t dimension : shape) {
        if (dimension <= 0 || elements > std::numeric_limits<std::size_t>::max() /
                                         static_cast<std::size_t>(dimension)) {
            throw std::runtime_error("NPU returned invalid output shape");
        }
        elements *= static_cast<std::size_t>(dimension);
    }
    return elements;
}

}  // namespace

int main() {
    try {
        unsigned long long cycle = 1;
        // 接入真实 CPU/gem5 producer 时，通常只替换 shape、values、dtype、DRAM 地址；
        // 后续“先 STORE、再通知 NPU、最后 LOAD 输出”的一致性协议保持不变。
        const std::vector<std::int64_t> input_shape = {1, 2, 8};
        const std::vector<float> input_values = {
            0.00F, 0.10F, 0.20F, 0.30F, 0.40F, 0.50F, 0.60F, 0.70F,
            0.80F, 0.90F, 1.00F, 1.10F, 1.20F, 1.30F, 1.40F, 1.50F};
        const NPUSim::TensorDType input_dtype = NPUSim::TensorDType::kBf16;
        const std::vector<std::uint8_t> input_payload =
            NPUSim::encodeFloatTensor(input_values, input_dtype);

        std::cout << "[CPU-ONNX][BOOT] CPU stores hidden state to DRAM, then sends only descriptor to NPU"
                  << std::endl;
        // 1) 先发布输入数据；NPU 收到 task 后会从同一地址执行 DMA_LOAD。
        storeBytesToDram(kHiddenStateDramAddress, input_payload, cycle);

        // 2) CPU -> NPU 只传任务/shape/dtype/DRAM 地址，不传 tensor payload。
        CpuNpuOnnxProtocol::NpuTaskDescriptor task;
        task.token = CpuNpuOnnxProtocol::kStartToken;
        task.input_count = 1;
        sendToNpu(task, cycle);
        CpuNpuOnnxProtocol::DramTensorDescriptor input;
        input.rank = checkedI64(input_shape.size(), "input rank");
        input.element_count = checkedI64(input_values.size(), "input element count");
        input.dtype = static_cast<std::int64_t>(input_dtype);
        input.dram_address = static_cast<std::int64_t>(kHiddenStateDramAddress);
        input.byte_count = checkedI64(input_payload.size(), "input byte count");
        sendToNpu(input, cycle);
        sendShapeToNpu(input_shape, cycle);

        // 3) 等 NPU 的 timing schedule 与所有 output DMA_STORE 都完成。
        CpuNpuOnnxProtocol::NpuCompletion completion;
        receiveFromNpu(completion, cycle);
        if (completion.status != CpuNpuOnnxProtocol::kSuccess ||
            completion.output_count <= 0 || completion.output_count > 1024) {
            throw std::runtime_error("NPU reported failed ONNX execution");
        }

        std::size_t total_elements = 0;
        for (std::int64_t index = 0; index < completion.output_count; ++index) {
            CpuNpuOnnxProtocol::DramTensorDescriptor output;
            receiveFromNpu(output, cycle);
            if (output.rank < 0 || output.rank > 16 || output.element_count < 0 ||
                output.dram_address < 0 || output.byte_count < 0 ||
                !NPUSim::isSupportedTensorDType(output.dtype)) {
                throw std::runtime_error("NPU returned invalid output DRAM descriptor");
            }
            const NPUSim::TensorDType dtype = NPUSim::tensorDTypeFromWire(output.dtype);
            std::vector<std::int64_t> shape(static_cast<std::size_t>(output.rank));
            if (!shape.empty()) {
                receiveShapeFromNpu(shape, cycle);
            }
            const std::size_t elements = checkedElementCount(shape);
            const std::size_t bytes = NPUSim::checkedTensorByteCount(elements, dtype);
            if (elements != static_cast<std::size_t>(output.element_count) ||
                bytes != static_cast<std::size_t>(output.byte_count)) {
                throw std::runtime_error("NPU output descriptor has inconsistent shape/dtype/bytes");
            }
            // 4) NPU 回传的是输出位置；CPU 仍通过 DRAM LOAD 取得真实结果。
            const std::vector<std::uint8_t> payload =
                loadBytesFromDram(static_cast<std::uint64_t>(output.dram_address), bytes, cycle);
            const std::vector<float> values = NPUSim::decodeFloatTensor(payload, dtype);
            total_elements += values.size();
            std::cout << "[CPU-ONNX][OUTPUT] index=" << index
                      << " elements=" << values.size()
                      << " dtype=" << NPUSim::tensorDTypeName(dtype)
                      << " first=" << (values.empty() ? 0.0F : values.front()) << std::endl;
        }

        // 5) NPU 在收到 ACK 前保持 DRAM server 存活，确保输出严格走
        // NPU -> DRAM -> CPU，而不是错误地通过 NPU -> CPU 控制通道传 tensor。
        CpuNpuOnnxProtocol::OutputConsumedAck ack;
        ack.token = CpuNpuOnnxProtocol::kOutputConsumedToken;
        sendToNpu(ack, cycle);
        std::cout << "[CPU-ONNX][DONE] outputs=" << completion.output_count
                  << " output_elements=" << total_elements
                  << " npu_finish_cycle=" << completion.finish_cycle
                  << " cpu_cycle=" << cycle << std::endl;
        InterChiplet::sendCycleCmd(cycle);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "[CPU-ONNX][ERROR] " << error.what() << std::endl;
        return 1;
    }
}

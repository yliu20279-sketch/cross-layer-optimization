#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <exception>
#include <fstream>
#include <future>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

#include "cpu_npu_onnx_protocol.h"
#include "onnx_event_lowering.h"
#include "pipe_comm.h"
#include "sync_protocol.h"
#include "npusim_chiplet_runtime.h"
#include "npusim_runtime.h"

namespace {

// 与 CPU workload/yml 一致的三芯粒坐标。NPU 在收到 CPU task 之前不解析 ONNX，
// 这样模型执行的起点由跨芯粒协议决定，而不是由进程启动时间决定。
constexpr int kCpuX = 0;
constexpr int kCpuY = 0;
constexpr int kNpuX = 1;
constexpr int kNpuY = 0;
constexpr std::size_t kMaxTransferBytes = 4096;

InterChiplet::PipeComm g_pipe_comm;

std::string environment(const char* key, const std::string& fallback = "") {
    // 片内 profile 与多轮 memory profile 都由 Makefile/InterChiplet 通过环境变量注入。
    const char* value = std::getenv(key);
    return value == nullptr || value[0] == '\0' ? fallback : std::string(value);
}

std::vector<char> readBinaryFile(const std::string& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input.is_open()) {
        throw std::runtime_error("cannot open ONNX model: " + path);
    }
    return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}

template <typename T>
void receivePayload(T& payload, unsigned long long& cycle) {
    // CPU -> NPU 控制元数据：task、输入描述符以及最终 ACK。
    const std::string pipe = InterChiplet::receiveSync(kCpuX, kCpuY, kNpuX, kNpuY);
    if (g_pipe_comm.read_data(pipe.c_str(), &payload, sizeof(T)) != static_cast<int>(sizeof(T))) {
        throw std::runtime_error("NPU failed to receive CPU task metadata");
    }
    cycle = InterChiplet::readSync(cycle, kCpuX, kCpuY, kNpuX, kNpuY, sizeof(T), 0);
}

void receiveBytes(void* buffer, std::size_t bytes, unsigned long long& cycle) {
    // 大 shape 元数据切块接收；此处不是从 CPU 接收 tensor payload。
    auto* cursor = static_cast<std::uint8_t*>(buffer);
    for (std::size_t offset = 0; offset < bytes;) {
        const std::size_t chunk = std::min(kMaxTransferBytes, bytes - offset);
        const std::string pipe = InterChiplet::receiveSync(kCpuX, kCpuY, kNpuX, kNpuY);
        if (g_pipe_comm.read_data(pipe.c_str(), cursor + offset, static_cast<int>(chunk)) !=
            static_cast<int>(chunk)) {
            throw std::runtime_error("NPU failed to receive CPU tensor metadata");
        }
        cycle = InterChiplet::readSync(cycle, kCpuX, kCpuY, kNpuX, kNpuY,
                                       static_cast<int>(chunk), 0);
        offset += chunk;
    }
}

template <typename T>
void sendPayload(const T& payload, unsigned long long& cycle) {
    // NPU -> CPU 控制元数据：完成状态和输出 tensor 的 DRAM 描述符。
    const std::string pipe = InterChiplet::sendSync(kNpuX, kNpuY, kCpuX, kCpuY);
    if (g_pipe_comm.write_data(pipe.c_str(), const_cast<T*>(&payload), sizeof(T)) !=
        static_cast<int>(sizeof(T))) {
        throw std::runtime_error("NPU failed to send CPU completion metadata");
    }
    cycle = InterChiplet::writeSync(cycle, kNpuX, kNpuY, kCpuX, kCpuY, sizeof(T), 0);
}

void sendBytes(const void* buffer, std::size_t bytes, unsigned long long& cycle) {
    const auto* cursor = static_cast<const std::uint8_t*>(buffer);
    for (std::size_t offset = 0; offset < bytes;) {
        const std::size_t chunk = std::min(kMaxTransferBytes, bytes - offset);
        const std::string pipe = InterChiplet::sendSync(kNpuX, kNpuY, kCpuX, kCpuY);
        if (g_pipe_comm.write_data(pipe.c_str(), const_cast<std::uint8_t*>(cursor + offset),
                                   static_cast<int>(chunk)) != static_cast<int>(chunk)) {
            throw std::runtime_error("NPU failed to send CPU tensor shape");
        }
        cycle = InterChiplet::writeSync(cycle, kNpuX, kNpuY, kCpuX, kCpuY,
                                        static_cast<int>(chunk), 0);
        offset += chunk;
    }
}

std::int64_t checkedI64(std::size_t value, const char* field) {
    if (value > static_cast<std::size_t>(std::numeric_limits<std::int64_t>::max())) {
        throw std::runtime_error(std::string("tensor ") + field + " exceeds int64 protocol range");
    }
    return static_cast<std::int64_t>(value);
}

std::uint64_t alignUp(std::uint64_t value, std::uint64_t alignment) {
    alignment = std::max<std::uint64_t>(1, alignment);
    const std::uint64_t remainder = value % alignment;
    if (remainder == 0) {
        return value;
    }
    if (value > std::numeric_limits<std::uint64_t>::max() - (alignment - remainder)) {
        throw std::runtime_error("DRAM address alignment overflow");
    }
    return value + alignment - remainder;
}

std::uint64_t checkedRangeEnd(std::uint64_t address, std::uint64_t bytes, const std::string& label) {
    if (bytes > std::numeric_limits<std::uint64_t>::max() - address) {
        throw std::runtime_error("DRAM range overflow for " + label);
    }
    return address + bytes;
}

bool rangesOverlap(std::uint64_t lhs_address, std::uint64_t lhs_bytes,
                   std::uint64_t rhs_address, std::uint64_t rhs_bytes) {
    return lhs_address < checkedRangeEnd(rhs_address, rhs_bytes, "overlap check") &&
           rhs_address < checkedRangeEnd(lhs_address, lhs_bytes, "overlap check");
}

struct SharedDramInputTensor {
    // CPU 输入 tensor 的控制信息与“DMA_LOAD 后才填充”的功能数据缓存。
    std::string graph_input_name;
    NPUSim::Tensor tensor;
    NPUSim::TensorDType dtype = NPUSim::TensorDType::kFp32;
    std::uint64_t address = 0;
    std::uint64_t byte_count = 0;
    std::vector<std::uint8_t> encoded_bytes;
    bool loaded = false;
};

SharedDramInputTensor receiveInputTensor(unsigned long long& cycle) {
    // CPU 传来的地址必须与 ONNX lowerer 中该 graph input 的 DMA_LOAD 地址一致。
    CpuNpuOnnxProtocol::DramTensorDescriptor descriptor;
    receivePayload(descriptor, cycle);
    if (descriptor.rank < 0 || descriptor.rank > 16 || descriptor.element_count < 0 ||
        descriptor.dram_address < 0 || descriptor.byte_count < 0 ||
        !NPUSim::isSupportedTensorDType(descriptor.dtype)) {
        throw std::runtime_error("CPU sent an unsupported input DRAM descriptor");
    }
    SharedDramInputTensor input;
    input.dtype = NPUSim::tensorDTypeFromWire(descriptor.dtype);
    input.address = static_cast<std::uint64_t>(descriptor.dram_address);
    input.byte_count = static_cast<std::uint64_t>(descriptor.byte_count);
    input.tensor.shape.resize(static_cast<std::size_t>(descriptor.rank));
    if (!input.tensor.shape.empty()) {
        receiveBytes(input.tensor.shape.data(),
                     input.tensor.shape.size() * sizeof(input.tensor.shape.front()), cycle);
    }
    std::size_t shape_elements = 1;
    for (const std::int64_t dim : input.tensor.shape) {
        if (dim <= 0 || shape_elements > std::numeric_limits<std::size_t>::max() /
                                        static_cast<std::size_t>(dim)) {
            throw std::runtime_error("CPU sent an invalid input tensor shape");
        }
        shape_elements *= static_cast<std::size_t>(dim);
    }
    if (shape_elements != static_cast<std::size_t>(descriptor.element_count) ||
        input.byte_count != NPUSim::checkedTensorByteCount(shape_elements, input.dtype)) {
        throw std::runtime_error("CPU input tensor descriptor has inconsistent shape/dtype/bytes");
    }
    return input;
}

std::vector<std::string> externalGraphInputs(const NPUSim::Model& model) {
    // ONNX initializer 是权重，不应当要求 CPU 通过协议提供；只返回真正运行时输入。
    std::vector<std::string> result;
    for (const std::string& name : model.graph_inputs) {
        if (model.initializers.count(name) == 0) {
            result.push_back(name);
        }
    }
    return result;
}

void applyTopology(NPUSim::NPUConfig& config, const std::string& topology_path) {
    // JSON 内的相对路径不依赖当前工作目录；实际片内拓扑由 Makefile 传绝对路径覆盖。
    if (topology_path.empty()) {
        throw std::runtime_error("NPUSIM_NPU_TOPOLOGY is required");
    }
    config.topology_mode = "custom_gv";
    config.topology_gv_path = topology_path;
}

void materializeStaticTensors(const NPUSim::Model& model,
                              const NPUSim::OnnxEventLoweringResult& lowered,
                              const NPUSim::NPUConfig& config,
                              NPUSim::ChipletNpuRuntime& runtime) {
    // initializer/Constant 走 NPU -> DRAM 的真实 STORE，随后 lower 后的 DMA_LOAD
    // 才能取回相同字节；这使功能模型和 timing 模型共享一条数据路径。
    std::set<std::string> materialized;
    const auto materialize = [&](const std::string& name, const NPUSim::Tensor& tensor) {
        if (!materialized.insert(name).second) {
            return;
        }
        const auto address = lowered.tensor_addresses.find(name);
        if (address == lowered.tensor_addresses.end()) {
            return;  // Static value is not used by a modeled DMA event.
        }
        const std::vector<std::uint8_t> payload =
            NPUSim::encodeFloatTensor(tensor.data, config.weight_dtype);
        runtime.store(address->second, payload.data(), payload.size(), "materialize_weight_" + name);
    };
    for (const auto& initializer : model.initializers) {
        materialize(initializer.first, initializer.second);
    }
    for (const NPUSim::Node& node : model.nodes) {
        if (node.op_type != "Constant" || node.outputs.empty() || node.outputs.front().empty()) {
            continue;
        }
        const auto value = node.tensor_attrs.find("value");
        if (value != node.tensor_attrs.end()) {
            materialize(node.outputs.front(), value->second);
        }
    }
}

}  // namespace

int main(int argc, char* argv[]) {
    unsigned long long cpu_to_npu_cycle = 1;
    bool cpu_task_received = false;
    std::shared_ptr<std::promise<void>> inputs_ready;
    bool inputs_ready_signaled = false;
    std::unique_ptr<NPUSim::ChipletNpuRuntime> runtime;
    try {
        if (argc != 4) {
            std::cerr << "usage: npu_onnx_chiplet_workload <model.onnx> <config.json> <report_dir>\n";
            return 1;
        }

        // 1) 等 CPU 发布输入到 DRAM 后发送 start token；没有 token 不开始 ONNX 调度。
        CpuNpuOnnxProtocol::NpuTaskDescriptor task;
        std::cout << "[NPU-ONNX-WRAPPER][WAIT] waiting CPU task descriptor" << std::endl;
        receivePayload(task, cpu_to_npu_cycle);
        cpu_task_received = true;
        if (task.token != CpuNpuOnnxProtocol::kStartToken || task.input_count <= 0 || task.input_count > 64) {
            throw std::runtime_error("CPU sent an invalid ONNX NPU task descriptor");
        }

        // 2) 接收输入描述符。tensor 数据仍在 DRAM，尚未进入 NPU 功能模型。
        std::vector<SharedDramInputTensor> shared_inputs;
        shared_inputs.reserve(static_cast<std::size_t>(task.input_count));
        for (std::int64_t index = 0; index < task.input_count; ++index) {
            shared_inputs.push_back(receiveInputTensor(cpu_to_npu_cycle));
        }

        // 3) 加载统一配置，并校验共享 DRAM 功能/时序模型的必要条件。
        NPUSim::NPUConfig config = NPUSim::loadConfig(argv[2]);
        applyTopology(config, environment("NPUSIM_NPU_TOPOLOGY"));
        if (!config.external_memory_enable || config.external_memory_model != "chiplet") {
            throw std::runtime_error("ONNX wrapper requires external_memory.model=chiplet");
        }
        if (!config.activation_dtype_explicit || !config.weight_dtype_explicit ||
            !config.accumulator_dtype_explicit || !config.output_dtype_explicit) {
            throw std::runtime_error("ONNX wrapper requires explicit activation/weight/accumulator/output dtype");
        }
        if (config.activation_dtype != config.output_dtype) {
            throw std::runtime_error(
                "current shared-DRAM ONNX wrapper requires activation_dtype == output_dtype; "
                "the lowerer uses one activation storage width");
        }
        if (!config.onnx_materialize_weights_to_dram) {
            throw std::runtime_error(
                "shared-DRAM ONNX wrapper requires onnx_materialize_weights_to_dram=true");
        }
        for (const SharedDramInputTensor& input : shared_inputs) {
            if (input.dtype != config.activation_dtype) {
                throw std::runtime_error("CPU input dtype must equal npu.activation_dtype");
            }
        }

        // 4) 解析 ONNX 与静态 shape；任何不支持算子或动态 shape 会在 lower 前后报错。
        const std::vector<char> model_bytes = readBinaryFile(argv[1]);
        const NPUSim::Model model = NPUSim::parseOnnxModel(model_bytes);
        const std::vector<std::string> graph_inputs = externalGraphInputs(model);
        if (graph_inputs.size() != shared_inputs.size()) {
            throw std::runtime_error("CPU input_count does not match ONNX non-initializer graph inputs");
        }

        std::uint64_t input_region_end = 0;
        for (std::size_t index = 0; index < shared_inputs.size(); ++index) {
            SharedDramInputTensor& input = shared_inputs[index];
            input.graph_input_name = graph_inputs[index];
            const auto expected_shape = model.value_shapes.find(input.graph_input_name);
            if (expected_shape == model.value_shapes.end() || expected_shape->second != input.tensor.shape) {
                throw std::runtime_error("CPU input shape does not match static ONNX graph input '" +
                                         input.graph_input_name + "'");
            }
            if (input.address > config.dram_size_bytes ||
                input.byte_count > config.dram_size_bytes - input.address) {
                throw std::runtime_error("CPU input tensor lies outside configured shared DRAM");
            }
            input_region_end = std::max(
                input_region_end,
                checkedRangeEnd(input.address, input.byte_count, "CPU input " + input.graph_input_name));
            for (std::size_t previous = 0; previous < index; ++previous) {
                const SharedDramInputTensor& other = shared_inputs[previous];
                if (rangesOverlap(input.address, input.byte_count, other.address, other.byte_count)) {
                    throw std::runtime_error("CPU graph input DRAM ranges overlap");
                }
            }
        }

        // 5) 地址布局：CPU 输入占低地址；中间 activation 紧跟其后；权重/Constant
        // 从上半区开始。显式检查重叠，避免 weight preload 覆盖 CPU hidden state。
        NPUSim::OnnxEventLoweringOptions lowering;
        lowering.activation_base_address = alignUp(input_region_end, config.dram_transaction_bytes);
        lowering.weight_base_address = config.dram_chiplet_region_bytes / 2;
        lowering.address_alignment_bytes = std::max<std::uint64_t>(1, config.dram_transaction_bytes);
        for (const SharedDramInputTensor& input : shared_inputs) {
            lowering.tensor_address_overrides.emplace(input.graph_input_name, input.address);
        }
        const NPUSim::OnnxEventLoweringResult lowered =
            NPUSim::lowerOnnxModelToProgramEvents(model, config, lowering);
        for (const SharedDramInputTensor& input : shared_inputs) {
            const auto address = lowered.tensor_addresses.find(input.graph_input_name);
            if (address == lowered.tensor_addresses.end() || address->second != input.address) {
                throw std::runtime_error("ONNX lowerer did not preserve CPU input DRAM address");
            }
        }
        std::set<std::string> static_tensor_names;
        for (const auto& initializer : model.initializers) {
            static_tensor_names.insert(initializer.first);
        }
        for (const NPUSim::Node& node : model.nodes) {
            if (node.op_type == "Constant" && !node.outputs.empty() && !node.outputs.front().empty()) {
                static_tensor_names.insert(node.outputs.front());
            }
        }
        // The simple graph allocator reserves one activation range and one
        // weight range.  Reject a model/config pair if the two regions meet;
        // otherwise a correct CPU input could be overwritten by weight preload.
        for (const auto& lhs : lowered.tensor_addresses) {
            const auto lhs_shape = lowered.inferred_value_shapes.find(lhs.first);
            if (lhs_shape == lowered.inferred_value_shapes.end()) {
                continue;
            }
            const bool lhs_static = static_tensor_names.count(lhs.first) != 0;
            const std::uint64_t lhs_bytes = NPUSim::checkedTensorByteCount(
                static_cast<std::size_t>(NPUSim::Tensor{lhs_shape->second, {}}.elements()),
                lhs_static ? config.weight_dtype : config.activation_dtype);
            for (const auto& rhs : lowered.tensor_addresses) {
                if (lhs.first >= rhs.first || lhs_static == (static_tensor_names.count(rhs.first) != 0)) {
                    continue;
                }
                const auto rhs_shape = lowered.inferred_value_shapes.find(rhs.first);
                if (rhs_shape == lowered.inferred_value_shapes.end()) {
                    continue;
                }
                const bool rhs_static = static_tensor_names.count(rhs.first) != 0;
                const std::uint64_t rhs_bytes = NPUSim::checkedTensorByteCount(
                    static_cast<std::size_t>(NPUSim::Tensor{rhs_shape->second, {}}.elements()),
                    rhs_static ? config.weight_dtype : config.activation_dtype);
                if (rangesOverlap(lhs.second, lhs_bytes, rhs.second, rhs_bytes)) {
                    throw std::runtime_error("ONNX activation and weight DRAM ranges overlap: '" +
                                             lhs.first + "' versus '" + rhs.first + "'");
                }
            }
        }

        // 6) Runtime 接收离线片内 PopNet profile。
        NPUSim::ChipletNpuRuntimeOptions options;
        options.self_x = kNpuX;
        options.self_y = kNpuY;
        options.initial_cycle = cpu_to_npu_cycle;
        options.report_directory = argv[3];
        options.intra_delay_profile_path = environment("NPUSIM_INTRA_DELAY_PROFILE");
        options.log_prefix = "[NPU-ONNX-WRAPPER][DRAM]";
        runtime = std::make_unique<NPUSim::ChipletNpuRuntime>(config, options);

        // 7) 冷启动预置权重/Constant；这些 STORE 也进入 DRAM/片间网络时序。
        materializeStaticTensors(model, lowered, config, *runtime);

        NPUSim::FunctionalOnnxExecutionOptions functional_options;
        functional_options.activation_dtype = config.activation_dtype;
        functional_options.weight_dtype = config.weight_dtype;
        functional_options.accumulator_dtype = config.accumulator_dtype;
        functional_options.output_dtype = config.output_dtype;
        functional_options.round_each_operator = config.functional_round_each_operator;
        inputs_ready = std::make_shared<std::promise<void>>();
        const std::shared_future<void> input_ready_future = inputs_ready->get_future().share();
        // 功能 ONNX 与 timing schedule 并行准备，但必须等对应输入 DMA_LOAD 把真实
        // 字节从 DRAM 取回，防止“功能结果早于数据到达”破坏一致性。
        const std::shared_future<NPUSim::FunctionalOnnxResult> functional_future = std::async(
            std::launch::async,
            [model_bytes, &shared_inputs, functional_options, input_ready_future]() {
                input_ready_future.get();
                std::vector<NPUSim::Tensor> inputs;
                inputs.reserve(shared_inputs.size());
                for (const SharedDramInputTensor& input : shared_inputs) {
                    if (!input.loaded) {
                        throw std::runtime_error("functional ONNX started before DMA input became ready");
                    }
                    inputs.push_back(input.tensor);
                }
                return NPUSim::runOnnxFunctionally(model_bytes, inputs, functional_options);
            }).share();

        // 8) 将 lower 后的 DMA 事件绑定到真实字节：输入 LOAD 完成时解码 tensor，
        // 输出 STORE 发生时编码功能结果。一个 DMA 同时承担功能和时序，不走旁路。
        NPUSim::ChipletDmaCallbackOptions dma_options;
        std::vector<bool> has_input_load(shared_inputs.size(), false);
        std::size_t loaded_input_count = 0;
        for (const NPUSim::NpuProgramEvent& event : lowered.events) {
            if (event.kind != NPUSim::NpuProgramEventKind::kDmaLoad) {
                continue;
            }
            for (std::size_t index = 0; index < shared_inputs.size(); ++index) {
                SharedDramInputTensor& input = shared_inputs[index];
                if (event.address != input.address || event.bytes != input.byte_count) {
                    continue;
                }
                has_input_load[index] = true;
                NPUSim::ChipletDmaPayloadBinding binding;
                binding.logical_id = event.id;
                binding.address = event.address;
                binding.bytes = event.bytes;
                binding.load_destination = &input.encoded_bytes;
                binding.label = "load_cpu_input_" + input.graph_input_name;
                binding.after_load = [&input, &loaded_input_count, &inputs_ready_signaled,
                                      &shared_inputs, inputs_ready]() {
                    if (input.loaded) {
                        return;
                    }
                    input.tensor.data = NPUSim::decodeFloatTensor(input.encoded_bytes, input.dtype);
                    input.loaded = true;
                    ++loaded_input_count;
                    if (loaded_input_count == shared_inputs.size()) {
                        inputs_ready->set_value();
                        inputs_ready_signaled = true;
                    }
                };
                dma_options.payload_bindings.push_back(std::move(binding));
            }
        }
        for (std::size_t index = 0; index < has_input_load.size(); ++index) {
            if (!has_input_load[index]) {
                throw std::runtime_error("ONNX lowering emitted no DMA_LOAD for CPU graph input '" +
                                         shared_inputs[index].graph_input_name + "'");
            }
        }

        // 每个 materialized ONNX tensor 绑定到其 DMA_STORE。lazy source 确保 store
        // 只在模型规定的 data-ready 周期取功能结果并写入 DRAM，而非另开数据通路。
        std::map<NPUSim::NpuEventId, std::string> store_tensor_names;
        for (const std::string& output : model.graph_outputs) {
            const auto ready = lowered.tensor_ready_events.find(output);
            if (ready != lowered.tensor_ready_events.end()) {
                store_tensor_names[ready->second] = output;
            }
        }
        for (const auto& ready : lowered.tensor_ready_events) {
            store_tensor_names.emplace(ready.second, ready.first);
        }
        const auto store_payloads =
            std::make_shared<std::map<NPUSim::NpuEventId, std::vector<std::uint8_t>>>();
        for (const auto& item : store_tensor_names) {
            const auto event = std::find_if(lowered.events.begin(), lowered.events.end(),
                [&item](const NPUSim::NpuProgramEvent& candidate) { return candidate.id == item.first; });
            if (event == lowered.events.end() || event->kind != NPUSim::NpuProgramEventKind::kDmaStore) {
                throw std::runtime_error("ONNX tensor ready event is not a DMA_STORE");
            }
            NPUSim::ChipletDmaPayloadBinding binding;
            binding.logical_id = event->id;
            binding.address = event->address;
            binding.bytes = event->bytes;
            binding.label = "store_onnx_tensor_" + item.second;
            binding.store_source = [functional_future, store_payloads, event_id = event->id,
                                    tensor_name = item.second, dtype = config.output_dtype]()
                                        -> const std::vector<std::uint8_t>& {
                const NPUSim::FunctionalOnnxResult& result = functional_future.get();
                const auto tensor = result.named_tensors.find(tensor_name);
                if (tensor == result.named_tensors.end()) {
                    throw std::runtime_error("functional ONNX result lacks materialized tensor '" + tensor_name + "'");
                }
                std::vector<std::uint8_t>& payload = (*store_payloads)[event_id];
                if (payload.empty()) {
                    payload = NPUSim::encodeFloatTensor(tensor->second.data, dtype);
                }
                return payload;
            };
            dma_options.payload_bindings.push_back(std::move(binding));
        }

        std::cout << "[NPU-ONNX-WRAPPER][START] inputs=" << shared_inputs.size()
                  << " events=" << lowered.events.size() << " NPU=(1,0) DRAM=("
                  << config.dram_chiplet_x << ',' << config.dram_chiplet_y << ')' << std::endl;
        // 9) 调度事件：DMA 的完成时间（含片内时序）会自然后移其
        // 依赖的 MAC/VECTOR/REDUCE；functional_future 只在输入到齐后才能完成。
        const NPUSim::NpuProgramScheduleResult schedule = runtime->scheduleProgram(lowered.events, dma_options);
        const NPUSim::FunctionalOnnxResult& functional = functional_future.get();
        if (functional.output_tensors.empty() || functional.output_tensors.size() != model.graph_outputs.size()) {
            throw std::runtime_error("functional ONNX output count does not match ONNX graph outputs");
        }

        // 10) 所有输出已 DMA_STORE 后，仅向 CPU 回传输出描述符；CPU 还需自行 LOAD。
        CpuNpuOnnxProtocol::NpuCompletion completion;
        completion.status = CpuNpuOnnxProtocol::kSuccess;
        completion.event_count = static_cast<std::int64_t>(lowered.events.size());
        completion.finish_cycle = static_cast<std::int64_t>(schedule.overall_finish_cycle);
        completion.output_count = checkedI64(functional.output_tensors.size(), "output count");
        unsigned long long return_cycle = runtime->chipCycle();
        sendPayload(completion, return_cycle);
        for (std::size_t index = 0; index < functional.output_tensors.size(); ++index) {
            const std::string& name = model.graph_outputs[index];
            const auto address = lowered.tensor_addresses.find(name);
            if (address == lowered.tensor_addresses.end()) {
                throw std::runtime_error("ONNX graph output has no shared DRAM address: " + name);
            }
            const NPUSim::Tensor& tensor = functional.output_tensors[index];
            CpuNpuOnnxProtocol::DramTensorDescriptor descriptor;
            descriptor.rank = checkedI64(tensor.shape.size(), "output rank");
            descriptor.element_count = checkedI64(tensor.data.size(), "output element count");
            descriptor.dtype = static_cast<std::int64_t>(config.output_dtype);
            descriptor.dram_address = static_cast<std::int64_t>(address->second);
            descriptor.byte_count = checkedI64(NPUSim::checkedTensorByteCount(tensor.data.size(), config.output_dtype),
                                               "output byte count");
            sendPayload(descriptor, return_cycle);
            if (!tensor.shape.empty()) {
                sendBytes(tensor.shape.data(), tensor.shape.size() * sizeof(tensor.shape.front()), return_cycle);
            }
        }

        // 11) 等 CPU 对每个输出完成 DRAM LOAD 后的 ACK，再关闭 DRAM server。
        // 这保证输出严格按 NPU -> DRAM -> CPU 传递。
        CpuNpuOnnxProtocol::OutputConsumedAck consumed;
        receivePayload(consumed, return_cycle);
        if (consumed.token != CpuNpuOnnxProtocol::kOutputConsumedToken) {
            throw std::runtime_error("CPU sent an invalid output-consumed acknowledgement");
        }

        runtime->chipCycle() = return_cycle;
        runtime->shutdown();
        const unsigned long long final_cycle = runtime->chipCycle();
        InterChiplet::sendCycleCmd(final_cycle);
        std::cout << "[NPU-ONNX-WRAPPER][DONE] finish_cycle=" << schedule.finish_cycle
                  << " external_finish_cycle=" << schedule.external_finish_cycle
                  << " overall_finish_cycle=" << schedule.overall_finish_cycle
                  << " final_cycle=" << final_cycle
                  << " outputs=" << functional.output_tensors.size()
                  << " injected_intra_cycles=" << schedule.injected_intra_cycles << std::endl;
        return 0;
    } catch (const std::exception& error) {
        if (inputs_ready && !inputs_ready_signaled) {
            try {
                inputs_ready->set_exception(std::make_exception_ptr(
                    std::runtime_error("NPU scheduling failed before all DRAM inputs were loaded")));
            } catch (...) {
            }
        }
        if (runtime) {
            try {
                runtime->shutdown();
            } catch (...) {
            }
        }
        // CPU 发送 task 后在等 completion。错误时仍回传失败记录，避免不支持算子或
        // 非法 descriptor 让 CPU 进程永久阻塞。
        if (cpu_task_received) {
            try {
                CpuNpuOnnxProtocol::NpuCompletion failed;
                failed.finish_cycle = static_cast<std::int64_t>(cpu_to_npu_cycle);
                sendPayload(failed, cpu_to_npu_cycle);
            } catch (...) {
            }
        }
        std::cerr << "[NPU-ONNX-WRAPPER][ERROR] " << error.what() << std::endl;
        return 1;
    }
}

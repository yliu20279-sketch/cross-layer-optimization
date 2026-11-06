#include "onnx_event_lowering.h"

#include <algorithm>
#include <limits>
#include <set>
#include <sstream>
#include <stdexcept>
#include <utility>

namespace NPUSim {
namespace {

using Shape = std::vector<std::int64_t>;

std::uint64_t checkedAdd(std::uint64_t left, std::uint64_t right, const std::string& what) {
    if (right > std::numeric_limits<std::uint64_t>::max() - left) {
        throw std::runtime_error("ONNX event lowering overflow while computing " + what);
    }
    return left + right;
}

std::uint64_t checkedMul(std::uint64_t left, std::uint64_t right, const std::string& what) {
    if (left != 0 && right > std::numeric_limits<std::uint64_t>::max() / left) {
        throw std::runtime_error("ONNX event lowering overflow while computing " + what);
    }
    return left * right;
}

Shape normalizeShape(const Shape& shape, const std::string& tensor_name) {
    Shape normalized = shape;
    for (std::int64_t& dim : normalized) {
        if (dim <= 0) {
            throw std::runtime_error("ONNX event lowering requires a positive static dimension for tensor '" +
                                     tensor_name + "'");
        }
    }
    return normalized;
}

std::uint64_t elementCount(const Shape& shape, const std::string& tensor_name) {
    std::uint64_t elements = 1;
    for (const std::int64_t dim : normalizeShape(shape, tensor_name)) {
        elements = checkedMul(elements, static_cast<std::uint64_t>(dim), "tensor element count");
    }
    return elements;
}

std::uint64_t byteCount(const Shape& shape,
                        std::uint64_t bytes_per_element,
                        const std::string& tensor_name) {
    return checkedMul(elementCount(shape, tensor_name),
                      std::max<std::uint64_t>(1, bytes_per_element),
                      "tensor byte count");
}

std::string nodeLabel(const Node& node, std::size_t index) {
    return node.name.empty() ? node.op_type + "_" + std::to_string(index) : node.name;
}

std::int64_t intAttr(const Node& node, const std::string& name, std::int64_t fallback) {
    const auto it = node.int_attrs.find(name);
    return it == node.int_attrs.end() ? fallback : it->second;
}

std::vector<std::int64_t> intsAttr(const Node& node, const std::string& name) {
    const auto it = node.ints_attrs.find(name);
    return it == node.ints_attrs.end() ? std::vector<std::int64_t>{} : it->second;
}

std::size_t normalizedAxis(std::int64_t axis, std::size_t rank, const std::string& context) {
    const std::int64_t normalized = axis < 0 ? axis + static_cast<std::int64_t>(rank) : axis;
    if (normalized < 0 || normalized >= static_cast<std::int64_t>(rank)) {
        throw std::runtime_error("invalid ONNX axis in " + context);
    }
    return static_cast<std::size_t>(normalized);
}

Shape broadcastShape(const Shape& left, const Shape& right, const std::string& context) {
    const std::size_t rank = std::max(left.size(), right.size());
    Shape output(rank, 1);
    for (std::size_t offset = 0; offset < rank; ++offset) {
        const std::int64_t left_dim =
            offset < left.size() ? left[left.size() - 1 - offset] : 1;
        const std::int64_t right_dim =
            offset < right.size() ? right[right.size() - 1 - offset] : 1;
        if (left_dim <= 0 || right_dim <= 0 ||
            (left_dim != right_dim && left_dim != 1 && right_dim != 1)) {
            throw std::runtime_error("incompatible ONNX broadcast shapes in " + context);
        }
        output[rank - 1 - offset] = std::max(left_dim, right_dim);
    }
    return output;
}

Shape matMulShape(const Shape& left, const Shape& right, const std::string& context) {
    if (left.size() < 2 || right.size() < 2) {
        throw std::runtime_error("ONNX MatMul requires rank >= 2 in " + context);
    }
    const std::int64_t k = left[left.size() - 1];
    const std::int64_t kb = right[right.size() - 2];
    if (k <= 0 || kb <= 0 || k != kb) {
        throw std::runtime_error("ONNX MatMul has incompatible K dimensions in " + context);
    }
    Shape left_batch(left.begin(), left.end() - 2);
    Shape right_batch(right.begin(), right.end() - 2);
    Shape output = broadcastShape(left_batch, right_batch, context);
    output.push_back(left[left.size() - 2]);
    output.push_back(right.back());
    return normalizeShape(output, context + " output");
}

Shape gemmShape(const Node& node, const Shape& left, const Shape& right, const std::string& context) {
    if (left.size() != 2 || right.size() != 2) {
        throw std::runtime_error("ONNX Gemm requires rank-2 tensors in " + context);
    }
    const bool trans_a = intAttr(node, "transA", 0) != 0;
    const bool trans_b = intAttr(node, "transB", 0) != 0;
    const std::int64_t m = trans_a ? left[1] : left[0];
    const std::int64_t k = trans_a ? left[0] : left[1];
    const std::int64_t kb = trans_b ? right[1] : right[0];
    const std::int64_t n = trans_b ? right[0] : right[1];
    if (m <= 0 || k <= 0 || kb <= 0 || n <= 0 || k != kb) {
        throw std::runtime_error("ONNX Gemm has incompatible dimensions in " + context);
    }
    return {m, n};
}

Shape convShape(const Node& node, const Shape& input, const Shape& weight, const std::string& context) {
    if (input.size() != 4 || weight.size() != 4) {
        throw std::runtime_error("ONNX Conv lowerer currently requires NCHW/OIHW tensors in " + context);
    }
    const std::vector<std::int64_t> strides = intsAttr(node, "strides");
    const std::vector<std::int64_t> pads = intsAttr(node, "pads");
    const std::vector<std::int64_t> dilations = intsAttr(node, "dilations");
    const std::int64_t stride_h = strides.size() >= 2 ? strides[0] : 1;
    const std::int64_t stride_w = strides.size() >= 2 ? strides[1] : 1;
    const std::int64_t dilation_h = dilations.size() >= 2 ? dilations[0] : 1;
    const std::int64_t dilation_w = dilations.size() >= 2 ? dilations[1] : 1;
    const std::int64_t pad_top = pads.size() >= 4 ? pads[0] : 0;
    const std::int64_t pad_left = pads.size() >= 4 ? pads[1] : 0;
    const std::int64_t pad_bottom = pads.size() >= 4 ? pads[2] : 0;
    const std::int64_t pad_right = pads.size() >= 4 ? pads[3] : 0;
    if (stride_h <= 0 || stride_w <= 0 || dilation_h <= 0 || dilation_w <= 0 ||
        input[0] <= 0 || input[1] <= 0 || input[2] <= 0 || input[3] <= 0 ||
        weight[0] <= 0 || weight[1] <= 0 || weight[2] <= 0 || weight[3] <= 0) {
        throw std::runtime_error("invalid static Conv shape/attribute in " + context);
    }
    const std::int64_t group = std::max<std::int64_t>(1, intAttr(node, "group", 1));
    if (input[1] != weight[1] * group) {
        throw std::runtime_error("ONNX Conv channel/group mismatch in " + context);
    }
    const std::int64_t effective_h = dilation_h * (weight[2] - 1) + 1;
    const std::int64_t effective_w = dilation_w * (weight[3] - 1) + 1;
    const std::int64_t out_h = (input[2] + pad_top + pad_bottom - effective_h) / stride_h + 1;
    const std::int64_t out_w = (input[3] + pad_left + pad_right - effective_w) / stride_w + 1;
    if (out_h <= 0 || out_w <= 0) {
        throw std::runtime_error("ONNX Conv output is non-positive in " + context);
    }
    return {input[0], weight[0], out_h, out_w};
}

Shape flattenShape(const Node& node, const Shape& input, const std::string& context) {
    const std::size_t axis = normalizedAxis(intAttr(node, "axis", 1), input.size(), context);
    std::uint64_t first = 1;
    std::uint64_t second = 1;
    for (std::size_t index = 0; index < axis; ++index) {
        first = checkedMul(first, static_cast<std::uint64_t>(input[index]), "Flatten dimension");
    }
    for (std::size_t index = axis; index < input.size(); ++index) {
        second = checkedMul(second, static_cast<std::uint64_t>(input[index]), "Flatten dimension");
    }
    if (first > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()) ||
        second > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())) {
        throw std::runtime_error("ONNX Flatten shape exceeds int64 range in " + context);
    }
    return {static_cast<std::int64_t>(first), static_cast<std::int64_t>(second)};
}

std::vector<std::int64_t> initializerI64(const Model& model,
                                         const std::string& name,
                                         const std::string& context) {
    const auto it = model.initializers.find(name);
    if (it == model.initializers.end()) {
        throw std::runtime_error("ONNX " + context + " requires initializer '" + name + "'");
    }
    std::vector<std::int64_t> result;
    result.reserve(it->second.data.size());
    for (const float value : it->second.data) {
        result.push_back(static_cast<std::int64_t>(value));
    }
    return result;
}

Shape reshapeShape(const Model& model,
                   const Node& node,
                   const Shape& input,
                   const std::string& context) {
    if (node.inputs.size() < 2 || node.inputs[1].empty()) {
        throw std::runtime_error("ONNX Reshape needs a static shape initializer in " + context);
    }
    const std::vector<std::int64_t> requested = initializerI64(model, node.inputs[1], "Reshape");
    if (requested.empty()) {
        throw std::runtime_error("ONNX Reshape has an empty target shape in " + context);
    }
    const std::uint64_t input_elements = elementCount(input, context + " input");
    Shape output;
    output.reserve(requested.size());
    int inferred_index = -1;
    std::uint64_t explicit_elements = 1;
    for (std::size_t index = 0; index < requested.size(); ++index) {
        std::int64_t dim = requested[index];
        if (dim == 0) {
            if (index >= input.size()) {
                throw std::runtime_error("ONNX Reshape zero dimension is out of range in " + context);
            }
            dim = input[index];
        }
        if (dim == -1) {
            if (inferred_index >= 0) {
                throw std::runtime_error("ONNX Reshape has multiple inferred dimensions in " + context);
            }
            inferred_index = static_cast<int>(index);
            output.push_back(1);
        } else if (dim <= 0) {
            throw std::runtime_error("ONNX Reshape has an invalid target dimension in " + context);
        } else {
            output.push_back(dim);
            explicit_elements = checkedMul(explicit_elements,
                                           static_cast<std::uint64_t>(dim),
                                           "Reshape dimension");
        }
    }
    if (inferred_index >= 0) {
        if (explicit_elements == 0 || input_elements % explicit_elements != 0) {
            throw std::runtime_error("ONNX Reshape inferred dimension is not integral in " + context);
        }
        output[static_cast<std::size_t>(inferred_index)] =
            static_cast<std::int64_t>(input_elements / explicit_elements);
    } else if (explicit_elements != input_elements) {
        throw std::runtime_error("ONNX Reshape changes element count in " + context);
    }
    return output;
}

Shape transposeShape(const Node& node, const Shape& input, const std::string& context) {
    std::vector<std::int64_t> permutation = intsAttr(node, "perm");
    if (permutation.empty()) {
        permutation.resize(input.size());
        for (std::size_t index = 0; index < input.size(); ++index) {
            permutation[index] = static_cast<std::int64_t>(input.size() - 1 - index);
        }
    }
    if (permutation.size() != input.size()) {
        throw std::runtime_error("ONNX Transpose has an invalid permutation in " + context);
    }
    Shape output(input.size(), 0);
    std::set<std::int64_t> seen;
    for (std::size_t index = 0; index < permutation.size(); ++index) {
        const std::int64_t dim = permutation[index];
        if (dim < 0 || dim >= static_cast<std::int64_t>(input.size()) || !seen.insert(dim).second) {
            throw std::runtime_error("ONNX Transpose has an invalid permutation in " + context);
        }
        output[index] = input[static_cast<std::size_t>(dim)];
    }
    return output;
}

std::vector<std::int64_t> reduceAxes(const Model& model,
                                     const Node& node,
                                     const Shape& input,
                                     const std::string& context) {
    std::vector<std::int64_t> axes = intsAttr(node, "axes");
    if (axes.empty() && node.inputs.size() >= 2 && !node.inputs[1].empty()) {
        axes = initializerI64(model, node.inputs[1], context + " axes");
    }
    if (axes.empty()) {
        axes.resize(input.size());
        for (std::size_t index = 0; index < input.size(); ++index) {
            axes[index] = static_cast<std::int64_t>(index);
        }
    }
    std::set<std::int64_t> unique;
    for (std::int64_t& axis : axes) {
        axis = axis < 0 ? axis + static_cast<std::int64_t>(input.size()) : axis;
        if (axis < 0 || axis >= static_cast<std::int64_t>(input.size()) || !unique.insert(axis).second) {
            throw std::runtime_error("ONNX " + context + " has invalid reduction axes");
        }
    }
    return axes;
}

Shape reduceShape(const Model& model, const Node& node, const Shape& input, const std::string& context) {
    const std::vector<std::int64_t> axes = reduceAxes(model, node, input, context);
    const bool keep_dims = intAttr(node, "keepdims", 1) != 0;
    std::set<std::int64_t> reduced(axes.begin(), axes.end());
    Shape output;
    for (std::size_t index = 0; index < input.size(); ++index) {
        if (reduced.count(static_cast<std::int64_t>(index)) != 0) {
            if (keep_dims) {
                output.push_back(1);
            }
        } else {
            output.push_back(input[index]);
        }
    }
    return output.empty() ? Shape{1} : output;
}

class AddressAllocator {
public:
    AddressAllocator(std::map<std::string, std::uint64_t>& addresses,
                     const OnnxEventLoweringOptions& options)
        : addresses_(addresses),
          activation_next_(options.activation_base_address),
          weight_next_(options.weight_base_address),
          alignment_(std::max<std::uint64_t>(1, options.address_alignment_bytes)),
          overrides_(options.tensor_address_overrides) {}

    std::uint64_t addressFor(const std::string& tensor_name, std::uint64_t bytes, bool weight) {
        const auto existing = addresses_.find(tensor_name);
        if (existing != addresses_.end()) {
            return existing->second;
        }
        const auto override = overrides_.find(tensor_name);
        if (override != overrides_.end()) {
            if (override->second % alignment_ != 0) {
                throw std::runtime_error("ONNX tensor address override is not aligned: " + tensor_name);
            }
            addresses_.emplace(tensor_name, override->second);
            return override->second;
        }
        std::uint64_t& next = weight ? weight_next_ : activation_next_;
        next = align(next);
        bytes = std::max<std::uint64_t>(1, bytes);
        if (bytes > std::numeric_limits<std::uint64_t>::max() - next) {
            throw std::runtime_error("ONNX event lowering address space overflow");
        }
        const std::uint64_t address = next;
        next = checkedAdd(next, bytes, "tensor address");
        addresses_.emplace(tensor_name, address);
        return address;
    }

private:
    std::uint64_t align(std::uint64_t value) const {
        const std::uint64_t remainder = value % alignment_;
        return remainder == 0 ? value : checkedAdd(value, alignment_ - remainder, "address alignment");
    }

    std::map<std::string, std::uint64_t>& addresses_;
    std::uint64_t activation_next_;
    std::uint64_t weight_next_;
    std::uint64_t alignment_;
    const std::map<std::string, std::uint64_t>& overrides_;
};

bool isVectorOperator(const std::string& op_type) {
    static const std::set<std::string> kVectorOperators = {
        "Add", "Sub", "Mul", "Div", "Pow", "Relu", "Sigmoid", "Tanh", "Neg", "Abs",
        "Exp", "Log", "Sqrt", "Reciprocal", "Rsqrt", "Erf", "Gelu", "SiLU", "LeakyRelu",
        "Clip", "Cast", "QuantizeLinear", "DequantizeLinear", "Where"};
    return kVectorOperators.count(op_type) != 0;
}

bool isReductionOperator(const std::string& op_type) {
    static const std::set<std::string> kReductionOperators = {
        "ReduceMean", "ReduceSum", "ReduceMax", "ReduceMin", "ReduceL1", "ReduceL2"};
    return kReductionOperators.count(op_type) != 0;
}

}  // namespace

OnnxEventLoweringResult lowerOnnxModelToProgramEvents(
    const Model& model,
    const NPUConfig& config,
    const OnnxEventLoweringOptions& options) {
    if (config.mac_unit_count <= 0) {
        throw std::runtime_error("ONNX event lowering requires at least one NPU MAC resource");
    }

    OnnxEventLoweringResult result;
    std::map<std::string, Shape> shapes = model.value_shapes;
    std::set<std::string> static_tensors;
    for (const auto& initializer : model.initializers) {
        shapes[initializer.first] = normalizeShape(initializer.second.shape, initializer.first);
        static_tensors.insert(initializer.first);
    }
    for (const std::string& input_name : model.graph_inputs) {
        const auto it = shapes.find(input_name);
        if (it != shapes.end()) {
            it->second = normalizeShape(it->second, input_name);
        }
    }

    NpuEventRecorder recorder;
    AddressAllocator addresses(result.tensor_addresses, options);
    // Each externally supplied graph input gets one explicit first DMA load at
    // the head of the program.  Besides making the data-ready dependency
    // visible, this lets a chiplet wrapper decode all real DRAM input bytes
    // before the first possible DMA_STORE asks for a functional result.  Its
    // first normal use reuses this event; later uses keep their own loads.
    std::map<std::string, NpuEventId> pending_graph_input_loads;

    const auto requireShape = [&](const std::string& tensor_name, const std::string& context) -> const Shape& {
        const auto it = shapes.find(tensor_name);
        if (it == shapes.end()) {
            throw std::runtime_error("ONNX event lowering lacks a static shape for tensor '" + tensor_name +
                                     "' consumed by " + context);
        }
        return it->second;
    };
    const auto inputBytes = [&](const std::string& tensor_name, const Shape& shape) -> std::uint64_t {
        const bool is_weight = static_tensors.count(tensor_name) != 0;
        return byteCount(shape,
                         is_weight ? config.weight_bytes : config.activation_bytes,
                         tensor_name);
    };
    const auto outputBytes = [&](const std::string& tensor_name, const Shape& shape) -> std::uint64_t {
        const std::uint64_t storage_width = std::max(config.activation_bytes, config.output_bytes);
        return byteCount(shape, storage_width, tensor_name);
    };
    const auto ensureAddress = [&](const std::string& tensor_name, const Shape& shape) -> std::uint64_t {
        const bool is_weight = static_tensors.count(tensor_name) != 0;
        return addresses.addressFor(tensor_name,
                                    is_weight
                                        ? byteCount(shape, config.weight_bytes, tensor_name)
                                        : outputBytes(tensor_name, shape),
                                    is_weight);
    };

    for (const auto& item : shapes) {
        ensureAddress(item.first, item.second);
    }

    const auto emitLoads = [&](const Node& node,
                               std::size_t input_count,
                               std::uint64_t desc,
                               const std::string& context) {
        std::vector<NpuEventId> loads;
        const std::size_t count = std::min(input_count, node.inputs.size());
        loads.reserve(count);
        for (std::size_t input_index = 0; input_index < count; ++input_index) {
            const std::string& name = node.inputs[input_index];
            if (name.empty()) {
                continue;
            }
            const Shape& shape = requireShape(name, context);
            const auto preload = pending_graph_input_loads.find(name);
            if (preload != pending_graph_input_loads.end()) {
                loads.push_back(preload->second);
                pending_graph_input_loads.erase(preload);
                continue;
            }
            const std::uint64_t address = ensureAddress(name, shape);
            const auto ready = result.tensor_ready_events.find(name);
            loads.push_back(recorder.dmaLoad(desc,
                                             address,
                                             inputBytes(name, shape),
                                             ready == result.tensor_ready_events.end()
                                                 ? std::vector<NpuEventId>{}
                                                 : std::vector<NpuEventId>{ready->second}));
        }
        return loads;
    };
    const auto emitMac = [&](std::uint64_t desc,
                             std::uint64_t operations,
                             const std::vector<NpuEventId>& dependencies) {
        std::vector<NpuEventId> mac_events;
        mac_events.reserve(static_cast<std::size_t>(config.mac_unit_count));
        const std::uint64_t mac_count = static_cast<std::uint64_t>(config.mac_unit_count);
        const std::uint64_t base = operations / mac_count;
        const std::uint64_t remainder = operations % mac_count;
        for (int mac_id = 0; mac_id < config.mac_unit_count; ++mac_id) {
            const std::uint64_t local_ops = base +
                (static_cast<std::uint64_t>(mac_id) < remainder ? 1ULL : 0ULL);
            if (local_ops != 0) {
                mac_events.push_back(recorder.macCompute(desc, local_ops, mac_id, dependencies));
            }
        }
        return recorder.barrier(desc, mac_events.empty() ? dependencies : mac_events);
    };
    const auto outputName = [](const Node& node, const std::string& context) -> const std::string& {
        if (node.outputs.empty() || node.outputs[0].empty()) {
            throw std::runtime_error("ONNX node has no primary output in " + context);
        }
        return node.outputs[0];
    };
    const auto emitStore = [&](std::uint64_t desc,
                               const std::string& name,
                               const Shape& shape,
                               NpuEventId completion) {
        shapes[name] = normalizeShape(shape, name);
        static_tensors.erase(name);
        const std::uint64_t address = ensureAddress(name, shapes.at(name));
        const NpuEventId store = recorder.dmaStore(desc,
                                                    address,
                                                    byteCount(shapes.at(name), config.output_bytes, name),
                                                    {completion});
        result.tensor_ready_events[name] = store;
    };
    const auto aliasOutput = [&](const std::string& output,
                                 const std::string& input,
                                 const Shape& shape) {
        shapes[output] = normalizeShape(shape, output);
        const bool input_is_static = static_tensors.count(input) != 0;
        if (input_is_static) {
            static_tensors.insert(output);
        } else {
            static_tensors.erase(output);
        }
        result.tensor_addresses[output] = ensureAddress(input, requireShape(input, output));
        const auto ready = result.tensor_ready_events.find(input);
        if (ready != result.tensor_ready_events.end()) {
            result.tensor_ready_events[output] = ready->second;
        }
    };

    // Preload only true graph inputs.  Initializers and Constant nodes are
    // materialized separately and continue to use their normal DMA loads.
    for (const std::string& input_name : model.graph_inputs) {
        if (static_tensors.count(input_name) != 0) {
            continue;
        }
        const Shape& shape = requireShape(input_name, "ONNX graph input");
        pending_graph_input_loads.emplace(
            input_name,
            recorder.dmaLoad(0,
                             ensureAddress(input_name, shape),
                             inputBytes(input_name, shape)));
    }

    for (std::size_t node_index = 0; node_index < model.nodes.size(); ++node_index) {
        const Node& node = model.nodes[node_index];
        const std::uint64_t desc = static_cast<std::uint64_t>(node_index + 1);
        const std::string context = "node '" + nodeLabel(node, node_index) + "' (" + node.op_type + ")";

        if (node.op_type == "Constant") {
            const auto value = node.tensor_attrs.find("value");
            if (value == node.tensor_attrs.end()) {
                throw std::runtime_error("ONNX Constant has no tensor value in " + context);
            }
            const std::string& output = outputName(node, context);
            shapes[output] = normalizeShape(value->second.shape, output);
            static_tensors.insert(output);
            ensureAddress(output, shapes.at(output));
            continue;
        }

        if (node.inputs.empty() || node.inputs[0].empty()) {
            throw std::runtime_error("ONNX event lowerer requires a primary input in " + context);
        }
        const std::string& output = outputName(node, context);

        if (node.op_type == "Identity" || node.op_type == "Dropout") {
            aliasOutput(output, node.inputs[0], requireShape(node.inputs[0], context));
            continue;
        }
        if (node.op_type == "Reshape") {
            aliasOutput(output,
                        node.inputs[0],
                        reshapeShape(model, node, requireShape(node.inputs[0], context), context));
            continue;
        }
        if (node.op_type == "Flatten") {
            aliasOutput(output,
                        node.inputs[0],
                        flattenShape(node, requireShape(node.inputs[0], context), context));
            continue;
        }

        if (node.op_type == "MatMul" || node.op_type == "Gemm") {
            if (node.inputs.size() < 2 || node.inputs[1].empty()) {
                throw std::runtime_error("ONNX " + node.op_type + " requires two inputs in " + context);
            }
            const Shape& left = requireShape(node.inputs[0], context);
            const Shape& right = requireShape(node.inputs[1], context);
            const Shape shape = node.op_type == "MatMul" ? matMulShape(left, right, context)
                                                            : gemmShape(node, left, right, context);
            const std::vector<NpuEventId> loads = emitLoads(node, node.inputs.size(), desc, context);
            const std::int64_t k = node.op_type == "MatMul"
                ? left[left.size() - 1]
                : (intAttr(node, "transA", 0) != 0 ? left[0] : left[1]);
            const std::uint64_t operations = checkedMul(
                checkedMul(2, elementCount(shape, output), "MatMul output operations"),
                static_cast<std::uint64_t>(k),
                "MatMul operations");
            NpuEventId completion = emitMac(desc, operations, loads);
            if (node.op_type == "Gemm" && node.inputs.size() >= 3 && !node.inputs[2].empty()) {
                completion = recorder.vectorCompute(desc, elementCount(shape, output), {completion});
            }
            emitStore(desc, output, shape, completion);
            continue;
        }

        if (node.op_type == "Conv") {
            if (node.inputs.size() < 2 || node.inputs[1].empty()) {
                throw std::runtime_error("ONNX Conv requires input and weight in " + context);
            }
            const Shape& input = requireShape(node.inputs[0], context);
            const Shape& weight = requireShape(node.inputs[1], context);
            const Shape shape = convShape(node, input, weight, context);
            const std::vector<NpuEventId> loads = emitLoads(node, node.inputs.size(), desc, context);
            const std::uint64_t per_output = checkedMul(
                checkedMul(static_cast<std::uint64_t>(weight[1]), static_cast<std::uint64_t>(weight[2]), "Conv kernel"),
                static_cast<std::uint64_t>(weight[3]),
                "Conv kernel");
            const std::uint64_t operations = checkedMul(
                checkedMul(2, elementCount(shape, output), "Conv output operations"),
                per_output,
                "Conv operations");
            NpuEventId completion = emitMac(desc, operations, loads);
            if (node.inputs.size() >= 3 && !node.inputs[2].empty()) {
                completion = recorder.vectorCompute(desc, elementCount(shape, output), {completion});
            }
            emitStore(desc, output, shape, completion);
            continue;
        }

        if (node.op_type == "Softmax" || node.op_type == "LogSoftmax") {
            const Shape shape = requireShape(node.inputs[0], context);
            const std::vector<NpuEventId> loads = emitLoads(node, 1, desc, context);
            const std::uint64_t elements = elementCount(shape, output);
            const NpuEventId shifted = recorder.vectorCompute(desc, elements, loads);
            const NpuEventId maximum = recorder.reduceCompute(desc, elements, {shifted});
            const NpuEventId exponentials = recorder.vectorCompute(desc, elements, {shifted, maximum});
            const NpuEventId denominator = recorder.reduceCompute(desc, elements, {exponentials});
            const NpuEventId normalized = recorder.vectorCompute(
                desc,
                node.op_type == "LogSoftmax" ? 2 * elements : elements,
                {exponentials, denominator});
            emitStore(desc, output, shape, normalized);
            continue;
        }

        if (node.op_type == "RMSNormalization") {
            if (node.inputs.size() < 2 || node.inputs[1].empty()) {
                throw std::runtime_error("ONNX RMSNormalization needs input and scale in " + context);
            }
            const Shape shape = requireShape(node.inputs[0], context);
            const std::vector<NpuEventId> loads = emitLoads(node, 2, desc, context);
            const std::uint64_t elements = elementCount(shape, output);
            const NpuEventId squares = recorder.vectorCompute(desc, elements, {loads.front()});
            const NpuEventId mean = recorder.reduceCompute(desc, elements, {squares});
            const NpuEventId scaled = recorder.vectorCompute(desc, 3 * elements, {loads[0], loads[1], mean});
            emitStore(desc, output, shape, scaled);
            continue;
        }

        if (node.op_type == "LayerNormalization") {
            if (node.inputs.size() < 2 || node.inputs[1].empty()) {
                throw std::runtime_error("ONNX LayerNormalization needs input and scale in " + context);
            }
            const Shape shape = requireShape(node.inputs[0], context);
            const std::vector<NpuEventId> loads = emitLoads(node, node.inputs.size(), desc, context);
            const std::uint64_t elements = elementCount(shape, output);
            const NpuEventId mean = recorder.reduceCompute(desc, elements, {loads.front()});
            const NpuEventId centered = recorder.vectorCompute(desc, elements, {loads.front(), mean});
            const NpuEventId squares = recorder.vectorCompute(desc, elements, {centered});
            const NpuEventId variance = recorder.reduceCompute(desc, elements, {squares});
            const NpuEventId normalized = recorder.vectorCompute(desc, 4 * elements, {centered, variance, loads[1]});
            emitStore(desc, output, shape, normalized);
            continue;
        }

        if (isReductionOperator(node.op_type)) {
            const Shape input = requireShape(node.inputs[0], context);
            const Shape shape = reduceShape(model, node, input, context);
            const std::vector<NpuEventId> loads = emitLoads(node, 1, desc, context);
            const NpuEventId reduction = recorder.reduceCompute(desc,
                                                                 elementCount(input, node.inputs[0]),
                                                                 loads);
            emitStore(desc, output, shape, reduction);
            continue;
        }

        if (node.op_type == "Transpose" || node.op_type == "Concat" || isVectorOperator(node.op_type)) {
            Shape shape;
            if (node.op_type == "Transpose") {
                shape = transposeShape(node, requireShape(node.inputs[0], context), context);
            } else if (node.op_type == "Concat") {
                const std::size_t axis = normalizedAxis(intAttr(node, "axis", 0),
                                                        requireShape(node.inputs[0], context).size(),
                                                        context);
                shape = requireShape(node.inputs[0], context);
                for (std::size_t input_index = 1; input_index < node.inputs.size(); ++input_index) {
                    const Shape& other = requireShape(node.inputs[input_index], context);
                    if (other.size() != shape.size()) {
                        throw std::runtime_error("ONNX Concat rank mismatch in " + context);
                    }
                    for (std::size_t dim = 0; dim < shape.size(); ++dim) {
                        if (dim == axis) {
                            const std::uint64_t concat_dim = checkedAdd(
                                static_cast<std::uint64_t>(shape[dim]),
                                static_cast<std::uint64_t>(other[dim]),
                                "Concat dimension");
                            if (concat_dim >
                                static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())) {
                                throw std::runtime_error("ONNX Concat dimension exceeds int64 range in " + context);
                            }
                            shape[dim] = static_cast<std::int64_t>(concat_dim);
                        } else if (shape[dim] != other[dim]) {
                            throw std::runtime_error("ONNX Concat dimension mismatch in " + context);
                        }
                    }
                }
            } else if (node.op_type == "Add" || node.op_type == "Sub" ||
                       node.op_type == "Mul" || node.op_type == "Div" || node.op_type == "Pow" ||
                       node.op_type == "Where") {
                if (node.inputs.size() < 2) {
                    throw std::runtime_error("ONNX elementwise op needs at least two inputs in " + context);
                }
                shape = requireShape(node.inputs[0], context);
                for (std::size_t input_index = 1; input_index < node.inputs.size(); ++input_index) {
                    shape = broadcastShape(shape, requireShape(node.inputs[input_index], context), context);
                }
            } else {
                shape = requireShape(node.inputs[0], context);
            }
            const std::vector<NpuEventId> loads = emitLoads(node, node.inputs.size(), desc, context);
            const std::uint64_t factor = node.op_type == "Gelu" || node.op_type == "SiLU" ? 4 : 1;
            const NpuEventId vector = recorder.vectorCompute(
                desc,
                checkedMul(factor, elementCount(shape, output), "vector operation count"),
                loads);
            emitStore(desc, output, shape, vector);
            continue;
        }

        const std::string unsupported = node.op_type + " in " + context;
        result.unsupported_operators.push_back(unsupported);
        if (options.fail_on_unsupported_operator) {
            throw std::runtime_error("unsupported ONNX operator for generic NPU event lowering: " + unsupported);
        }
        // Explicitly requested non-strict mode uses a conservative vector
        // fallback, never a zero-cycle skip.  A static output shape still has
        // to be supplied by ONNX value_info or a preceding shape pass.
        const Shape shape = requireShape(output, context + " output");
        const std::vector<NpuEventId> loads = emitLoads(node, node.inputs.size(), desc, context);
        const NpuEventId fallback = recorder.vectorCompute(desc, elementCount(shape, output), loads);
        emitStore(desc, output, shape, fallback);
    }

    result.events = recorder.events();
    result.inferred_value_shapes = std::move(shapes);
    return result;
}

OnnxEventLoweringResult lowerOnnxBytesToProgramEvents(
    const std::vector<char>& model_bytes,
    const NPUConfig& config,
    const OnnxEventLoweringOptions& options) {
    return lowerOnnxModelToProgramEvents(parseOnnxModel(model_bytes), config, options);
}

}  // namespace NPUSim

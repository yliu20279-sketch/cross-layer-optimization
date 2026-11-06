#include "npusim_runtime.h"

#include <cstdint>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

#include <onnx/onnx_pb.h>
#include <onnx/shape_inference/implementation.h>

namespace NPUSim {
namespace {

template <typename T>
T readRawLittleEndian(const std::string& bytes, std::size_t offset) {
    if (offset + sizeof(T) > bytes.size()) {
        throw std::runtime_error("official ONNX parser found truncated TensorProto raw_data");
    }
    T value{};
    std::memcpy(&value, bytes.data() + offset, sizeof(T));
    return value;
}

float halfToFloat(std::uint16_t bits) {
    const std::uint32_t sign = static_cast<std::uint32_t>(bits & 0x8000U) << 16U;
    int exponent = static_cast<int>((bits >> 10U) & 0x1FU);
    std::uint32_t mantissa = bits & 0x03FFU;
    std::uint32_t out_bits = 0;
    if (exponent == 0) {
        if (mantissa == 0) {
            out_bits = sign;
        } else {
            exponent = 1;
            while ((mantissa & 0x0400U) == 0) {
                mantissa <<= 1U;
                --exponent;
            }
            mantissa &= 0x03FFU;
            out_bits = sign | ((exponent + 112U) << 23U) | (mantissa << 13U);
        }
    } else if (exponent == 31) {
        out_bits = sign | 0x7F800000U | (mantissa << 13U);
    } else {
        out_bits = sign | (static_cast<std::uint32_t>(exponent + 112) << 23U) |
                   (mantissa << 13U);
    }
    float value = 0.0F;
    std::memcpy(&value, &out_bits, sizeof(value));
    return value;
}

float bfloat16ToFloat(std::uint16_t bits) {
    const std::uint32_t out_bits = static_cast<std::uint32_t>(bits) << 16U;
    float value = 0.0F;
    std::memcpy(&value, &out_bits, sizeof(value));
    return value;
}

std::uint64_t elementCount(const ONNX_NAMESPACE::TensorProto& tensor) {
    std::uint64_t elements = 1;
    for (const std::int64_t dim : tensor.dims()) {
        if (dim < 0 ||
            (dim != 0 && elements > std::numeric_limits<std::uint64_t>::max() /
                                             static_cast<std::uint64_t>(dim))) {
            throw std::runtime_error("official ONNX parser found an invalid TensorProto dimension");
        }
        elements *= static_cast<std::uint64_t>(dim);
    }
    return elements;
}

void requireElementCount(std::size_t actual,
                         std::uint64_t expected,
                         const std::string& tensor_name) {
    if (expected > static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max()) ||
        actual != static_cast<std::size_t>(expected)) {
        throw std::runtime_error("official ONNX parser found inconsistent payload size for initializer '" +
                                 tensor_name + "'");
    }
}

template <typename T>
void decodeRawNumeric(const std::string& raw,
                      std::uint64_t elements,
                      Tensor& output,
                      const std::string& tensor_name) {
    if (elements > static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max()) ||
        raw.size() != static_cast<std::size_t>(elements) * sizeof(T)) {
        throw std::runtime_error("official ONNX parser found inconsistent raw_data size for initializer '" +
                                 tensor_name + "'");
    }
    output.data.reserve(static_cast<std::size_t>(elements));
    for (std::size_t offset = 0; offset < raw.size(); offset += sizeof(T)) {
        output.data.push_back(static_cast<float>(readRawLittleEndian<T>(raw, offset)));
    }
}

Tensor convertTensor(const ONNX_NAMESPACE::TensorProto& source) {
    if (source.data_location() == ONNX_NAMESPACE::TensorProto::EXTERNAL) {
        throw std::runtime_error(
            "official ONNX parser does not load external TensorProto data from a byte payload; "
            "materialize external data before passing the model to NPUSim");
    }
    Tensor output;
    output.shape.assign(source.dims().begin(), source.dims().end());
    switch (source.data_type()) {
        case ONNX_NAMESPACE::TensorProto::INT64:
        case ONNX_NAMESPACE::TensorProto::UINT64:
        case ONNX_NAMESPACE::TensorProto::INT32:
        case ONNX_NAMESPACE::TensorProto::INT16:
        case ONNX_NAMESPACE::TensorProto::UINT16:
        case ONNX_NAMESPACE::TensorProto::INT8:
        case ONNX_NAMESPACE::TensorProto::UINT8:
        case ONNX_NAMESPACE::TensorProto::BOOL:
            output.integer_semantics = true;
            break;
        default:
            break;
    }
    const std::uint64_t elements = elementCount(source);
    const std::string tensor_name = source.name().empty() ? "<unnamed>" : source.name();
    if (elements == 0) {
        return output;
    }

    const std::string& raw = source.raw_data();
    switch (source.data_type()) {
        case ONNX_NAMESPACE::TensorProto::FLOAT:
            if (!raw.empty()) {
                decodeRawNumeric<float>(raw, elements, output, tensor_name);
            } else {
                requireElementCount(static_cast<std::size_t>(source.float_data_size()), elements, tensor_name);
                output.data.assign(source.float_data().begin(), source.float_data().end());
            }
            break;
        case ONNX_NAMESPACE::TensorProto::DOUBLE:
            if (!raw.empty()) {
                decodeRawNumeric<double>(raw, elements, output, tensor_name);
            } else {
                requireElementCount(static_cast<std::size_t>(source.double_data_size()), elements, tensor_name);
                output.data.reserve(static_cast<std::size_t>(elements));
                for (const double value : source.double_data()) {
                    output.data.push_back(static_cast<float>(value));
                }
            }
            break;
        case ONNX_NAMESPACE::TensorProto::INT64:
            if (!raw.empty()) {
                decodeRawNumeric<std::int64_t>(raw, elements, output, tensor_name);
            } else {
                requireElementCount(static_cast<std::size_t>(source.int64_data_size()), elements, tensor_name);
                output.data.reserve(static_cast<std::size_t>(elements));
                for (const std::int64_t value : source.int64_data()) {
                    output.data.push_back(static_cast<float>(value));
                }
            }
            break;
        case ONNX_NAMESPACE::TensorProto::UINT64:
            if (!raw.empty()) {
                decodeRawNumeric<std::uint64_t>(raw, elements, output, tensor_name);
            } else {
                requireElementCount(static_cast<std::size_t>(source.uint64_data_size()), elements, tensor_name);
                output.data.reserve(static_cast<std::size_t>(elements));
                for (const std::uint64_t value : source.uint64_data()) {
                    output.data.push_back(static_cast<float>(value));
                }
            }
            break;
        case ONNX_NAMESPACE::TensorProto::INT32:
            if (!raw.empty()) {
                decodeRawNumeric<std::int32_t>(raw, elements, output, tensor_name);
            } else {
                requireElementCount(static_cast<std::size_t>(source.int32_data_size()), elements, tensor_name);
                output.data.reserve(static_cast<std::size_t>(elements));
                for (const std::int32_t value : source.int32_data()) {
                    output.data.push_back(static_cast<float>(value));
                }
            }
            break;
        case ONNX_NAMESPACE::TensorProto::FLOAT16:
        case ONNX_NAMESPACE::TensorProto::BFLOAT16: {
            const bool bfloat = source.data_type() == ONNX_NAMESPACE::TensorProto::BFLOAT16;
            output.data.reserve(static_cast<std::size_t>(elements));
            if (!raw.empty()) {
                if (raw.size() != static_cast<std::size_t>(elements) * sizeof(std::uint16_t)) {
                    throw std::runtime_error("official ONNX parser found inconsistent FP16/BF16 raw_data size for initializer '" +
                                             tensor_name + "'");
                }
                for (std::size_t offset = 0; offset < raw.size(); offset += sizeof(std::uint16_t)) {
                    const std::uint16_t value = readRawLittleEndian<std::uint16_t>(raw, offset);
                    output.data.push_back(bfloat ? bfloat16ToFloat(value) : halfToFloat(value));
                }
            } else {
                requireElementCount(static_cast<std::size_t>(source.int32_data_size()), elements, tensor_name);
                for (const std::int32_t value : source.int32_data()) {
                    const std::uint16_t bits = static_cast<std::uint16_t>(value);
                    output.data.push_back(bfloat ? bfloat16ToFloat(bits) : halfToFloat(bits));
                }
            }
            break;
        }
        case ONNX_NAMESPACE::TensorProto::INT8:
        case ONNX_NAMESPACE::TensorProto::INT16:
        case ONNX_NAMESPACE::TensorProto::UINT8:
        case ONNX_NAMESPACE::TensorProto::UINT16:
        case ONNX_NAMESPACE::TensorProto::BOOL:
            if (!raw.empty()) {
                const std::size_t byte_width =
                    source.data_type() == ONNX_NAMESPACE::TensorProto::INT16 ||
                            source.data_type() == ONNX_NAMESPACE::TensorProto::UINT16
                        ? 2
                        : 1;
                if (raw.size() != static_cast<std::size_t>(elements) * byte_width) {
                    throw std::runtime_error("official ONNX parser found inconsistent integer raw_data size for initializer '" +
                                             tensor_name + "'");
                }
                output.data.reserve(static_cast<std::size_t>(elements));
                for (std::size_t index = 0; index < static_cast<std::size_t>(elements); ++index) {
                    const std::size_t offset = index * byte_width;
                    switch (source.data_type()) {
                        case ONNX_NAMESPACE::TensorProto::INT8:
                            output.data.push_back(static_cast<float>(readRawLittleEndian<std::int8_t>(raw, offset)));
                            break;
                        case ONNX_NAMESPACE::TensorProto::UINT8:
                        case ONNX_NAMESPACE::TensorProto::BOOL:
                            output.data.push_back(static_cast<float>(readRawLittleEndian<std::uint8_t>(raw, offset)));
                            break;
                        case ONNX_NAMESPACE::TensorProto::INT16:
                            output.data.push_back(static_cast<float>(readRawLittleEndian<std::int16_t>(raw, offset)));
                            break;
                        default:
                            output.data.push_back(static_cast<float>(readRawLittleEndian<std::uint16_t>(raw, offset)));
                            break;
                    }
                }
            } else {
                requireElementCount(static_cast<std::size_t>(source.int32_data_size()), elements, tensor_name);
                output.data.reserve(static_cast<std::size_t>(elements));
                for (const std::int32_t value : source.int32_data()) {
                    output.data.push_back(static_cast<float>(value));
                }
            }
            break;
        default:
            throw std::runtime_error("official ONNX parser does not yet materialize initializer data type " +
                                     std::to_string(source.data_type()) + " for '" + tensor_name + "'");
    }
    return output;
}

std::vector<std::int64_t> convertShape(const ONNX_NAMESPACE::ValueInfoProto& value) {
    std::vector<std::int64_t> shape;
    if (!value.has_type() || !value.type().has_tensor_type() ||
        !value.type().tensor_type().has_shape()) {
        return shape;
    }
    for (const auto& dimension : value.type().tensor_type().shape().dim()) {
        shape.push_back(dimension.has_dim_value() ? dimension.dim_value() : -1);
    }
    return shape;
}

void captureValueInfo(const ONNX_NAMESPACE::ValueInfoProto& value, Model& model) {
    if (value.name().empty()) {
        return;
    }
    const std::vector<std::int64_t> shape = convertShape(value);
    if (!shape.empty()) {
        model.value_shapes[value.name()] = shape;
    }
}

Node convertNode(const ONNX_NAMESPACE::NodeProto& source, int index) {
    Node output;
    output.name = source.name().empty() ? source.op_type() + "_" + std::to_string(index) : source.name();
    output.op_type = source.op_type();
    output.inputs.assign(source.input().begin(), source.input().end());
    output.outputs.assign(source.output().begin(), source.output().end());
    for (const auto& attribute : source.attribute()) {
        if (attribute.name().empty()) {
            continue;
        }
        switch (attribute.type()) {
            case ONNX_NAMESPACE::AttributeProto::INT:
                output.int_attrs[attribute.name()] = attribute.i();
                break;
            case ONNX_NAMESPACE::AttributeProto::FLOAT:
                output.float_attrs[attribute.name()] = attribute.f();
                break;
            case ONNX_NAMESPACE::AttributeProto::INTS:
                output.ints_attrs[attribute.name()] =
                    std::vector<std::int64_t>(attribute.ints().begin(), attribute.ints().end());
                break;
            case ONNX_NAMESPACE::AttributeProto::TENSOR:
                output.tensor_attrs[attribute.name()] = convertTensor(attribute.t());
                break;
            default:
                // The current functional/runtime Node representation has no
                // graph, string or sparse-tensor attribute field.  Retaining
                // the official ModelProto still lets unsupported operators be
                // rejected by the function/lowering stage rather than by a
                // lossy parser.
                break;
        }
    }
    return output;
}

Model convertModel(const ONNX_NAMESPACE::ModelProto& source) {
    if (!source.has_graph()) {
        throw std::runtime_error("official ONNX parser received a ModelProto without graph");
    }
    Model model;
    const ONNX_NAMESPACE::GraphProto& graph = source.graph();
    for (const auto& initializer : graph.initializer()) {
        if (initializer.name().empty()) {
            throw std::runtime_error("official ONNX parser found unnamed graph initializer");
        }
        model.initializers.emplace(initializer.name(), convertTensor(initializer));
        model.value_shapes[initializer.name()] = model.initializers.at(initializer.name()).shape;
    }
    for (const auto& value : graph.input()) {
        model.graph_inputs.push_back(value.name());
        captureValueInfo(value, model);
    }
    for (const auto& value : graph.output()) {
        model.graph_outputs.push_back(value.name());
        captureValueInfo(value, model);
    }
    for (const auto& value : graph.value_info()) {
        captureValueInfo(value, model);
    }
    int index = 0;
    for (const auto& node : graph.node()) {
        model.nodes.push_back(convertNode(node, index++));
    }
    return model;
}

}  // namespace

Model parseOnnxModel(const std::vector<char>& bytes) {
    if (bytes.empty()) {
        throw std::runtime_error("empty ONNX model payload");
    }
    if (bytes.size() > static_cast<std::size_t>(std::numeric_limits<int>::max())) {
        throw std::runtime_error("ONNX model payload exceeds protobuf ParseFromArray limit");
    }
    ONNX_NAMESPACE::ModelProto model_proto;
    if (!model_proto.ParseFromArray(bytes.data(), static_cast<int>(bytes.size()))) {
        throw std::runtime_error("official ONNX protobuf parser rejected ModelProto payload");
    }

    // Use the official schema registry and shape inference before translating
    // to NPUSim's execution/lowering IR.  Do not reject a graph merely because
    // a custom-domain operator has no registered shape function: existing
    // value_info remains available and the lowerer will give the precise
    // unsupported-op or missing-static-shape diagnostic later.
    ONNX_NAMESPACE::ModelProto inferred = model_proto;
    try {
        ONNX_NAMESPACE::ShapeInferenceOptions options;
        options.check_type = false;
        options.error_mode = 0;
        options.enable_data_propagation = true;
        ONNX_NAMESPACE::shape_inference::InferShapes(
            inferred, ONNX_NAMESPACE::OpSchemaRegistry::Instance(), options);
    } catch (const std::exception&) {
        inferred = model_proto;
    }
    return convertModel(inferred);
}

}  // namespace NPUSim

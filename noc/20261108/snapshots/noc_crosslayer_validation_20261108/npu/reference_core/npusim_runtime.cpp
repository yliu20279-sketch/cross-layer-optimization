#include "npusim_runtime.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <deque>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <numeric>
#include <queue>
#include <set>
#include <sstream>
#include <stdexcept>
#include <unordered_map>
#include <utility>

#include <nlohmann/json.hpp>

namespace NPUSim {
#if defined(__GNUC__) && !defined(NPUSIM_REQUIRE_OFFICIAL_ONNX)
// Direct-MatMul artifact binaries may link only the runtime object.  Keep that
// legacy direct path independent of ONNX, while every ONNX entry point built
// by NPUSim CMake links the strong official parser from
// onnx_official_parser.cpp.
extern Model parseOnnxModel(const std::vector<char>& bytes) __attribute__((weak));
#endif

namespace {

constexpr std::uint64_t kSpmAccessBytes = 64;

std::uint64_t ceilDiv(std::uint64_t a, std::uint64_t b) {
    b = std::max<std::uint64_t>(1, b);
    return (a + b - 1) / b;
}

std::uint64_t productU64(const std::vector<std::int64_t>& shape) {
    std::uint64_t total = 1;
    for (std::int64_t dim : shape) {
        total *= static_cast<std::uint64_t>(std::max<std::int64_t>(1, dim));
    }
    return total;
}

std::string readFileToString(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in.is_open()) {
        return {};
    }
    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

std::string dirnameOf(const std::string& path) {
    const std::size_t pos = path.find_last_of("/\\");
    if (pos == std::string::npos) {
        return {};
    }
    return path.substr(0, pos);
}

bool isAbsolutePath(const std::string& path) {
    if (path.empty()) {
        return false;
    }
#ifdef _WIN32
    return path.size() >= 2 && std::isalpha(static_cast<unsigned char>(path[0])) && path[1] == ':';
#else
    return path[0] == '/';
#endif
}

std::string joinPath(const std::string& base, const std::string& path) {
    if (path.empty() || isAbsolutePath(path) || base.empty()) {
        return path;
    }
    const char last = base.back();
    if (last == '/' || last == '\\') {
        return base + path;
    }
    return base + "/" + path;
}

struct TopologyEdge {
    int src = 0;
    int dst = 0;
    std::uint64_t weight = 1;
};

struct MacProfile {
    int mac_id = 0;
    int node_id = 0;
    int degree = 0;
    std::uint64_t distance_to_controller = 0;
    std::uint64_t sram_bytes = 0;
    std::uint64_t ops_per_cycle = 0;
};

struct RuntimeTopology {
    int node_count = 0;
    int controller_node = 0;
    std::string gv_path;
    std::vector<TopologyEdge> edges;
    std::vector<std::vector<std::pair<int, std::uint64_t>>> adj;
    std::vector<std::uint64_t> distance_from_controller;
    std::vector<MacProfile> macs;
};

struct WorkShard {
    int mac_id = 0;
    int node_id = 0;
    std::int64_t begin = 0;
    std::int64_t end = 0;
};

struct ShardActivity {
    std::uint64_t ops = 0;
    std::uint64_t bytes = 0;
    std::uint64_t spm_read_bytes = 0;
    std::uint64_t spm_write_bytes = 0;
    std::uint64_t spm_miss_bytes = 0;
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

struct OpActivity {
    std::uint64_t work_items = 0;
    std::uint64_t ops = 0;
    std::uint64_t bytes = 0;
    std::vector<WorkShard> shards;
    std::vector<ShardActivity> shard_activity;
};

struct ExternalAccessStats {
    std::uint64_t cycles = 0;
    std::uint64_t read_transactions = 0;
    std::uint64_t write_transactions = 0;
};

bool isIntegerToken(const std::string& token) {
    if (token.empty()) {
        return false;
    }
    std::size_t i = token[0] == '-' ? 1 : 0;
    if (i >= token.size()) {
        return false;
    }
    for (; i < token.size(); ++i) {
        if (!std::isdigit(static_cast<unsigned char>(token[i]))) {
            return false;
        }
    }
    return true;
}
// Instead of fully parsing Graphviz, split topology file into tokens for subsequent code to extract integer nodes, undirected edges and integer weights
std::vector<std::string> tokenizeDot(const std::string& text) {
    std::vector<std::string> tokens;
    for (std::size_t i = 0; i < text.size();) {
        const char c = text[i];
        if (std::isspace(static_cast<unsigned char>(c))) {
            ++i;
            continue;
        }
        if (c == '/' && i + 1 < text.size() && text[i + 1] == '/') {
            i += 2;
            while (i < text.size() && text[i] != '\n') {
                ++i;
            }
            continue;
        }
        if (c == '/' && i + 1 < text.size() && text[i + 1] == '*') {
            i += 2;
            while (i + 1 < text.size() && !(text[i] == '*' && text[i + 1] == '/')) {
                ++i;
            }
            i = std::min(text.size(), i + 2);
            continue;
        }
        if (c == '#') {
            while (i < text.size() && text[i] != '\n') {
                ++i;
            }
            continue;
        }
        if (c == '-' && i + 1 < text.size() && text[i + 1] == '-') {
            tokens.push_back("--");
            i += 2;
            continue;
        }
        if (std::string("{}[]=;,").find(c) != std::string::npos) {
            tokens.emplace_back(1, c);
            ++i;
            continue;
        }
        if (c == '"') {
            ++i;
            std::string token;
            while (i < text.size() && text[i] != '"') {
                if (text[i] == '\\' && i + 1 < text.size()) {
                    ++i;
                }
                token.push_back(text[i++]);
            }
            if (i < text.size() && text[i] == '"') {
                ++i;
            }
            tokens.push_back(token);
            continue;
        }
        std::string token;
        while (i < text.size()) {
            const char ch = text[i];
            if (std::isspace(static_cast<unsigned char>(ch)) ||
                std::string("{}[]=;,").find(ch) != std::string::npos ||
                (ch == '-' && i + 1 < text.size() && text[i + 1] == '-')) {
                break;
            }
            token.push_back(ch);
            ++i;
        }
        if (!token.empty()) {
            tokens.push_back(token);
        } else {
            ++i;
        }
    }
    return tokens;
}

std::uint64_t readAttrWeight(const std::vector<std::string>& tokens,
                             std::size_t& i,
                             std::uint64_t fallback) {
    if (i >= tokens.size() || tokens[i] != "[") {
        return fallback;
    }
    std::uint64_t weight = fallback;
    int depth = 0;
    for (; i < tokens.size(); ++i) {
        if (tokens[i] == "[") {
            ++depth;
        } else if (tokens[i] == "]") {
            --depth;
            if (depth == 0) {
                ++i;
                break;
            }
        } else if (tokens[i] == "weight" && i + 2 < tokens.size() && tokens[i + 1] == "=" &&
                   isIntegerToken(tokens[i + 2])) {
            weight = static_cast<std::uint64_t>(std::max(1, std::stoi(tokens[i + 2])));
        }
    }
    return weight;
}

std::vector<TopologyEdge> parseGvEdges(const std::string& path,
                                       std::set<int>& nodes,
                                       std::uint64_t& default_weight) {
    const std::string text = readFileToString(path);
    if (text.empty()) {
        throw std::runtime_error("cannot read NPU topology gv file: " + path);
    }
    const std::vector<std::string> tokens = tokenizeDot(text);
    std::vector<TopologyEdge> edges;
    default_weight = 1;
    for (std::size_t i = 0; i < tokens.size();) {
        if (tokens[i] == "edge") {
            ++i;
            default_weight = readAttrWeight(tokens, i, default_weight);
            continue;
        }
        if (!isIntegerToken(tokens[i])) {
            ++i;
            continue;
        }
        const int first = std::stoi(tokens[i++]);
        nodes.insert(first);
        if (i < tokens.size() && tokens[i] == "--") {
            std::vector<int> chain{first};
            while (i < tokens.size() && tokens[i] == "--") {
                ++i;
                if (i >= tokens.size() || !isIntegerToken(tokens[i])) {
                    throw std::runtime_error("malformed edge chain in gv topology: " + path);
                }
                const int node = std::stoi(tokens[i++]);
                nodes.insert(node);
                chain.push_back(node);
            }
            std::uint64_t weight = default_weight;
            if (i < tokens.size() && tokens[i] == "[") {
                weight = readAttrWeight(tokens, i, default_weight);
            }
            for (std::size_t e = 0; e + 1 < chain.size(); ++e) {
                edges.push_back({chain[e], chain[e + 1], weight});
            }
        } else if (i < tokens.size() && tokens[i] == "[") {
            (void)readAttrWeight(tokens, i, default_weight);
        }
    }
    return edges;
}

std::vector<std::uint64_t> dijkstraFrom(
    int source,
    const std::vector<std::vector<std::pair<int, std::uint64_t>>>& adj) {
    constexpr std::uint64_t kInf = std::numeric_limits<std::uint64_t>::max() / 4;
    std::vector<std::uint64_t> dist(adj.size(), kInf);
    using Item = std::pair<std::uint64_t, int>;
    std::priority_queue<Item, std::vector<Item>, std::greater<Item>> pq;
    dist[static_cast<std::size_t>(source)] = 0;
    pq.push({0, source});
    while (!pq.empty()) {
        const auto [d, u] = pq.top();
        pq.pop();
        if (d != dist[static_cast<std::size_t>(u)]) {
            continue;
        }
        for (const auto& [v, w] : adj[static_cast<std::size_t>(u)]) {
            const std::uint64_t nd = d + std::max<std::uint64_t>(1, w);
            if (nd < dist[static_cast<std::size_t>(v)]) {
                dist[static_cast<std::size_t>(v)] = nd;
                pq.push({nd, v});
            }
        }
    }
    return dist;
}

RuntimeTopology buildRuntimeTopology(const NPUConfig& cfg) {
    RuntimeTopology topo;
    topo.controller_node = cfg.controller_local_id;
    topo.gv_path = cfg.topology_gv_path;

    if (cfg.topology_mode != "custom_gv" || topo.gv_path.empty()) {
        throw std::runtime_error(
            "NPUSim requires an explicit custom_gv topology. Pass --topology-gv from the benchmark yml "
            "or NPUSIM_TOPOLOGY_GV from the local debug environment.");
    }

    std::set<int> nodes;
    std::uint64_t default_weight = 1;
    topo.edges = parseGvEdges(topo.gv_path, nodes, default_weight);
    (void)default_weight;

    if (cfg.mac_nodes.empty()) {
        throw std::runtime_error(
            "NPUSim requires npu.topology.mac_nodes in the JSON config. The simulator does not "
            "derive MAC nodes from mac_unit_count or assume a default topology.");
    }
    std::vector<int> mac_nodes = cfg.mac_nodes;
    if (mac_nodes.size() != static_cast<std::size_t>(cfg.mac_unit_count)) {
        std::ostringstream oss;
        oss << "invalid NPU topology: mac_nodes has " << mac_nodes.size()
            << " entries, mac_unit_count is " << cfg.mac_unit_count;
        throw std::runtime_error(oss.str());
    }

    int max_node = topo.controller_node;
    for (int node : nodes) {
        max_node = std::max(max_node, node);
    }
    for (int node : mac_nodes) {
        max_node = std::max(max_node, node);
        nodes.insert(node);
    }
    nodes.insert(topo.controller_node);
    topo.node_count = std::max(cfg.topology_node_count, max_node + 1);
    if (topo.node_count <= 0) {
        throw std::runtime_error("invalid NPU topology: node_count must be positive");
    }
    topo.adj.assign(static_cast<std::size_t>(topo.node_count), {});
    for (const auto& edge : topo.edges) {
        if (edge.src < 0 || edge.dst < 0 || edge.src >= topo.node_count || edge.dst >= topo.node_count) {
            throw std::runtime_error("gv topology edge endpoint exceeds configured node_count");
        }
        topo.adj[static_cast<std::size_t>(edge.src)].push_back({edge.dst, edge.weight});
        topo.adj[static_cast<std::size_t>(edge.dst)].push_back({edge.src, edge.weight});
    }
    if (topo.controller_node < 0 || topo.controller_node >= topo.node_count) {
        throw std::runtime_error("NPU controller_node is outside topology node range");
    }
    topo.distance_from_controller = dijkstraFrom(topo.controller_node, topo.adj);

    std::set<int> seen_macs;
    topo.macs.reserve(mac_nodes.size());
    constexpr std::uint64_t kInf = std::numeric_limits<std::uint64_t>::max() / 4;
    for (std::size_t mac_id = 0; mac_id < mac_nodes.size(); ++mac_id) {
        const int node = mac_nodes[mac_id];
        if (node < 0 || node >= topo.node_count) {
            throw std::runtime_error("NPU mac_nodes entry is outside topology node range");
        }
        if (node == topo.controller_node) {
            throw std::runtime_error("NPU MAC node cannot reuse controller_node");
        }
        if (!seen_macs.insert(node).second) {
            throw std::runtime_error("NPU mac_nodes contains duplicate node id");
        }
        const std::uint64_t dist = topo.distance_from_controller[static_cast<std::size_t>(node)];
        if (dist >= kInf) {
            std::ostringstream oss;
            oss << "NPU MAC node " << node << " is not reachable from controller node " << topo.controller_node;
            throw std::runtime_error(oss.str());
        }
        MacProfile mac;
        mac.mac_id = static_cast<int>(mac_id);
        mac.node_id = node;
        mac.degree = static_cast<int>(topo.adj[static_cast<std::size_t>(node)].size());
        mac.distance_to_controller = dist;
        mac.sram_bytes = cfg.sram_per_mac_bytes;
        mac.ops_per_cycle = cfg.mac_ops_per_cycle;
        topo.macs.push_back(mac);
    }
    return topo;
}

std::vector<WorkShard> buildLinearSchedule(std::int64_t work_items,
                                           std::uint64_t bytes,
                                           const RuntimeTopology& topo) {
    if (work_items <= 0 || topo.macs.empty()) {
        return {};
    }
    std::vector<double> weights;
    weights.reserve(topo.macs.size());
    const std::uint64_t expected_bytes_per_mac =
        ceilDiv(std::max<std::uint64_t>(1, bytes), static_cast<std::uint64_t>(topo.macs.size()));
    double total_weight = 0.0;
    for (const auto& mac : topo.macs) {
        const double spm_factor =
            expected_bytes_per_mac <= mac.sram_bytes
                ? 1.0
                : std::max(0.10, static_cast<double>(mac.sram_bytes) /
                                     static_cast<double>(std::max<std::uint64_t>(1, expected_bytes_per_mac)));
        const double distance_factor = 1.0 / (1.0 + static_cast<double>(mac.distance_to_controller));
        const double degree_factor = 1.0 + 0.05 * static_cast<double>(std::max(0, mac.degree - 1));
        const double w = std::max(1.0, static_cast<double>(mac.ops_per_cycle)) * spm_factor *
                         distance_factor * degree_factor;
        weights.push_back(w);
        total_weight += w;
    }
    if (total_weight <= 0.0) {
        total_weight = static_cast<double>(weights.size());
        std::fill(weights.begin(), weights.end(), 1.0);
    }

    std::vector<WorkShard> shards;
    std::int64_t begin = 0;
    double cumulative = 0.0;
    for (std::size_t idx = 0; idx < topo.macs.size(); ++idx) {
        cumulative += static_cast<double>(work_items) * weights[idx] / total_weight;
        std::int64_t end = (idx + 1 == topo.macs.size())
                               ? work_items
                               : static_cast<std::int64_t>(std::llround(cumulative));
        end = std::max(begin, std::min<std::int64_t>(work_items, end));
        if (end > begin) {
            shards.push_back({topo.macs[idx].mac_id, topo.macs[idx].node_id, begin, end});
        }
        begin = end;
    }
    return shards;
}

std::uint64_t scaleCycles(std::uint64_t cycles, double scale) {
    if (cycles == 0) {
        return 0;
    }
    return std::max<std::uint64_t>(
        1,
        static_cast<std::uint64_t>(std::llround(static_cast<double>(cycles) *
                                                std::max(0.0, scale))));
}

enum class ExternalMemoryTimingMode {
    kDisabled,
    kStandaloneAnalytic,
    kJointChiplet,
};

ExternalMemoryTimingMode selectExternalMemoryTimingMode(const NPUConfig& cfg) {
    if (!cfg.external_memory_enable || cfg.external_memory_model == "none") {
        return ExternalMemoryTimingMode::kDisabled;
    }
    if (cfg.external_memory_model == "analytic") {
        return ExternalMemoryTimingMode::kStandaloneAnalytic;
    }
    if (cfg.external_memory_model == "chiplet") {
        return ExternalMemoryTimingMode::kJointChiplet;
    }
    throw std::runtime_error("unsupported NPUSim external_memory.model: " + cfg.external_memory_model);
}

class ExternalMemoryAccounting {
  public:
    explicit ExternalMemoryAccounting(const NPUConfig& cfg)
        : cfg_(cfg), mode_(selectExternalMemoryTimingMode(cfg)) {}

    ExternalAccessStats access(bool is_write, std::uint64_t bytes) {
        ExternalAccessStats stats;
        if (mode_ == ExternalMemoryTimingMode::kDisabled || bytes == 0) {
            return stats;
        }
        const std::uint64_t tx_bytes =
            std::max<std::uint64_t>(1, cfg_.dram_transaction_bytes);
        const std::uint64_t txns = ceilDiv(bytes, tx_bytes);
        if (is_write) {
            stats.write_transactions = txns;
        } else {
            stats.read_transactions = txns;
        }

        // Joint LEGOSim mode keeps the traffic counters here, but the service
        // latency belongs to the separate LPDDR5 chiplet and its PopNet
        // completion path.  NPUSim should not add a local DRAM delay.
        if (mode_ == ExternalMemoryTimingMode::kJointChiplet) {
            return stats;
        }
        if (mode_ == ExternalMemoryTimingMode::kStandaloneAnalytic) {
            const std::uint64_t fixed =
                is_write ? cfg_.dram_write_fixed_latency_cycles
                         : cfg_.dram_read_fixed_latency_cycles;
            const std::uint64_t transfer =
                ceilDiv(bytes, std::max<std::uint64_t>(1, cfg_.ddr_bandwidth_bytes_per_cycle));
            stats.cycles = scaleCycles(fixed + transfer + ceilDiv(txns, 4),
                                       cfg_.dram_cycle_scale);
            return stats;
        }
        return stats;
    }

  private:
    const NPUConfig& cfg_;
    ExternalMemoryTimingMode mode_ = ExternalMemoryTimingMode::kDisabled;
};

std::vector<std::int64_t> shapeForExternalInput(const Model& model, const std::string& name, std::size_t count) {
    auto it = model.value_shapes.find(name);
    if (it != model.value_shapes.end() && productU64(it->second) == count) {
        return it->second;
    }
    return {static_cast<std::int64_t>(count)};
}

Tensor tensorFromI64(const std::vector<std::int64_t>& src, const std::vector<std::int64_t>& shape) {
    Tensor t;
    t.integer_semantics = true;
    t.shape = shape.empty() ? std::vector<std::int64_t>{static_cast<std::int64_t>(src.size())} : shape;
    t.data.reserve(src.size());
    for (std::int64_t value : src) {
        t.data.push_back(static_cast<float>(value));
    }
    const std::size_t elems = static_cast<std::size_t>(productU64(t.shape));
    if (t.data.size() < elems) {
        t.data.resize(elems, 0.0f);
    } else if (t.data.size() > elems && elems > 0) {
        t.data.resize(elems);
    }
    return t;
}

Tensor normalizeExternalFunctionalInput(const Tensor& source,
                                        const std::vector<std::int64_t>& target_shape,
                                        const std::string& input_name) {
    if (target_shape.empty()) {
        throw std::runtime_error("functional ONNX input '" + input_name +
                                 "' lacks a static shape");
    }
    const std::size_t target_elements = static_cast<std::size_t>(productU64(target_shape));
    if (target_elements == 0) {
        throw std::runtime_error("functional ONNX input '" + input_name +
                                 "' has an empty static shape");
    }
    if (source.data.empty()) {
        throw std::runtime_error("functional ONNX input '" + input_name + "' has no data");
    }
    Tensor normalized;
    normalized.shape = target_shape;
    normalized.integer_semantics = source.integer_semantics;
    if (source.data.size() == target_elements) {
        normalized.data = source.data;
        return normalized;
    }
    // A scalar descriptor/value sent by a CPU may represent a constant input
    // activation in a smoke test.  Do not silently pad or truncate arbitrary
    // tensors: only this explicit scalar broadcast is permitted.
    if (source.data.size() == 1) {
        normalized.data.assign(target_elements, source.data.front());
        return normalized;
    }
    throw std::runtime_error("functional ONNX input '" + input_name + "' has " +
                             std::to_string(source.data.size()) + " elements, expected " +
                             std::to_string(target_elements) + " (or one scalar to broadcast)");
}

std::vector<std::int64_t> normalizeAxisShape(std::vector<std::int64_t> shape) {
    if (shape.empty()) {
        shape.push_back(1);
    }
    for (auto& dim : shape) {
        dim = std::max<std::int64_t>(1, dim);
    }
    return shape;
}

std::int64_t offsetOf(const std::vector<std::int64_t>& shape, const std::vector<std::int64_t>& idx) {
    std::int64_t off = 0;
    for (std::size_t i = 0; i < shape.size(); ++i) {
        off = off * std::max<std::int64_t>(1, shape[i]) + idx[i];
    }
    return off;
}

std::vector<std::int64_t> unravel(std::int64_t linear, const std::vector<std::int64_t>& shape) {
    std::vector<std::int64_t> idx(shape.size(), 0);
    for (std::size_t rev = 0; rev < shape.size(); ++rev) {
        const std::size_t i = shape.size() - 1 - rev;
        const std::int64_t dim = std::max<std::int64_t>(1, shape[i]);
        idx[i] = linear % dim;
        linear /= dim;
    }
    return idx;
}

Tensor elementwiseBinary(const Tensor& a, const Tensor& b, const std::string& op) {
    const std::size_t rank = std::max(a.shape.size(), b.shape.size());
    std::vector<std::int64_t> out_shape(rank, 1);
    std::vector<std::int64_t> a_shape(rank, 1);
    std::vector<std::int64_t> b_shape(rank, 1);
    std::copy_backward(a.shape.begin(), a.shape.end(), a_shape.end());
    std::copy_backward(b.shape.begin(), b.shape.end(), b_shape.end());
    for (std::size_t i = 0; i < rank; ++i) {
        out_shape[i] = std::max(a_shape[i], b_shape[i]);
    }
    Tensor out;
    out.integer_semantics = a.integer_semantics && b.integer_semantics;
    out.shape = out_shape;
    out.data.assign(static_cast<std::size_t>(productU64(out_shape)), 0.0f);
    for (std::size_t linear = 0; linear < out.data.size(); ++linear) {
        const auto idx = unravel(static_cast<std::int64_t>(linear), out_shape);
        std::vector<std::int64_t> ai(rank, 0);
        std::vector<std::int64_t> bi(rank, 0);
        for (std::size_t d = 0; d < rank; ++d) {
            ai[d] = (a_shape[d] == 1) ? 0 : idx[d];
            bi[d] = (b_shape[d] == 1) ? 0 : idx[d];
        }
        const float av = a.data[static_cast<std::size_t>(offsetOf(a_shape, ai))];
        const float bv = b.data[static_cast<std::size_t>(offsetOf(b_shape, bi))];
        if (op == "Add") {
            out.data[linear] = av + bv;
        } else if (op == "Sub") {
            out.data[linear] = av - bv;
        } else if (op == "Mul") {
            out.data[linear] = av * bv;
        } else if (op == "Div") {
            out.data[linear] = bv == 0.0f ? 0.0f : av / bv;
        } else if (op == "Pow") {
            out.data[linear] = std::pow(av, bv);
        }
    }
    return out;
}

Tensor unary(const Tensor& x, const std::string& op) {
    Tensor out = x;
    for (float& value : out.data) {
        if (op == "Relu") {
            value = std::max(0.0f, value);
        } else if (op == "Sigmoid") {
            value = 1.0f / (1.0f + std::exp(-value));
        } else if (op == "Tanh") {
            value = std::tanh(value);
        } else if (op == "Neg") {
            value = -value;
        } else if (op == "Abs") {
            value = std::fabs(value);
        } else if (op == "Exp") {
            value = std::exp(value);
        } else if (op == "Log") {
            value = std::log(value);
        } else if (op == "Sqrt") {
            value = std::sqrt(std::max(0.0f, value));
        } else if (op == "Reciprocal") {
            value = value == 0.0f ? 0.0f : 1.0f / value;
        } else if (op == "Rsqrt") {
            value = value <= 0.0f ? 0.0f : 1.0f / std::sqrt(value);
        } else if (op == "Erf") {
            value = std::erf(value);
        } else if (op == "SiLU") {
            value = value / (1.0f + std::exp(-value));
        } else if (op == "Gelu") {
            value = 0.5f * value *
                    (1.0f + std::erf(value / std::sqrt(2.0f)));
        }
    }
    return out;
}

Tensor matmul2D(const Tensor& a,
                 const Tensor& b,
                 const RuntimeTopology& topology,
                 std::uint64_t& ops,
                 TensorDType accumulator_dtype = TensorDType::kFp32) {
    if (a.shape.size() < 2 || b.shape.size() < 2) {
        throw std::runtime_error("MatMul expects tensors with rank >= 2");
    }
    const std::int64_t m = a.shape[a.shape.size() - 2];
    const std::int64_t k = a.shape[a.shape.size() - 1];
    const std::int64_t kb = b.shape[b.shape.size() - 2];
    const std::int64_t n = b.shape[b.shape.size() - 1];
    if (k != kb) {
        throw std::runtime_error("MatMul shape mismatch");
    }
    const bool simple_rank2 = a.shape.size() == 2 && b.shape.size() == 2;
    const std::size_t output_batch_rank =
        std::max(a.shape.size(), b.shape.size()) - 2;
    std::vector<std::int64_t> output_batch_shape(output_batch_rank, 1);
    for (std::size_t reverse = 0; reverse < output_batch_rank; ++reverse) {
        const std::int64_t a_dim = reverse < a.shape.size() - 2
            ? a.shape[a.shape.size() - 3 - reverse] : 1;
        const std::int64_t b_dim = reverse < b.shape.size() - 2
            ? b.shape[b.shape.size() - 3 - reverse] : 1;
        if (a_dim <= 0 || b_dim <= 0 || (a_dim != b_dim && a_dim != 1 && b_dim != 1)) {
            throw std::runtime_error("MatMul batch dimensions are not broadcast-compatible");
        }
        output_batch_shape[output_batch_rank - 1 - reverse] = std::max(a_dim, b_dim);
    }
    Tensor out;
    out.shape = output_batch_shape;
    out.shape.push_back(m);
    out.shape.push_back(n);
    out.data.assign(static_cast<std::size_t>(productU64(out.shape)), 0.0f);

    const auto batchOffset = [&](const Tensor& tensor,
                                 const std::vector<std::int64_t>& output_batch_index) {
        const std::size_t tensor_batch_rank = tensor.shape.size() - 2;
        std::uint64_t offset = 0;
        for (std::size_t dim = 0; dim < tensor_batch_rank; ++dim) {
            const std::int64_t tensor_dim = tensor.shape[dim];
            const std::size_t output_dim = output_batch_rank - tensor_batch_rank + dim;
            const std::int64_t coordinate = tensor_dim == 1 ? 0 : output_batch_index[output_dim];
            offset = offset * static_cast<std::uint64_t>(tensor_dim) +
                     static_cast<std::uint64_t>(coordinate);
        }
        return offset * static_cast<std::uint64_t>(tensor.shape[tensor.shape.size() - 2]) *
               static_cast<std::uint64_t>(tensor.shape.back());
    };

    const std::uint64_t batch_count = productU64(output_batch_shape);
    for (std::uint64_t batch = 0; batch < batch_count; ++batch) {
        const std::vector<std::int64_t> batch_index =
            unravel(static_cast<std::int64_t>(batch), output_batch_shape);
        const std::uint64_t a_base = batchOffset(a, batch_index);
        const std::uint64_t b_base = batchOffset(b, batch_index);
        const std::uint64_t out_base = batch * static_cast<std::uint64_t>(m) * static_cast<std::uint64_t>(n);
        for (std::int64_t i = 0; i < m; ++i) {
            for (std::int64_t j = 0; j < n; ++j) {
                float sum = 0.0f;
                for (std::int64_t kk = 0; kk < k; ++kk) {
                    sum += a.data[static_cast<std::size_t>(a_base +
                                                           static_cast<std::uint64_t>(i * k + kk))] *
                           b.data[static_cast<std::size_t>(b_base +
                                                           static_cast<std::uint64_t>(kk * n + j))];
                    sum = convertFloatForTensorDType(sum, accumulator_dtype);
                }
                out.data[static_cast<std::size_t>(out_base +
                                                   static_cast<std::uint64_t>(i * n + j))] = sum;
            }
        }
    }
    // Keep the legacy topology-aware sharding for the standard rank-2
    // functional path.  Batched functional MatMul below is deliberately
    // serial/reference-only; timing comes from the separate ONNX lowerer.
    if (simple_rank2) {
        const std::uint64_t work_bytes =
            static_cast<std::uint64_t>(std::max<std::int64_t>(1, m * n)) * sizeof(float) +
            static_cast<std::uint64_t>(std::max<std::int64_t>(1, m * k + k * n)) * sizeof(float);
        (void)buildLinearSchedule(m, work_bytes, topology);
    }
    ops = 2ULL * batch_count * static_cast<std::uint64_t>(m) *
          static_cast<std::uint64_t>(n) * static_cast<std::uint64_t>(k);
    return out;
}

Tensor reduceTensor(const Tensor& x,
                    const std::vector<std::int64_t>& axes_argument,
                    bool keep_dims,
                    const std::string& op) {
    if (x.shape.empty()) {
        return x;
    }
    std::vector<bool> reduce_axis(x.shape.size(), false);
    std::vector<std::int64_t> axes = axes_argument;
    bool reduce_all = false;
    if (axes.empty()) {
        // ONNX opset 13+ distinguishes an omitted axes input (reduce all)
        // from an explicitly supplied empty axes tensor (reduce nothing).
        reduce_all = true;
    }
    if (reduce_all) {
        std::fill(reduce_axis.begin(), reduce_axis.end(), true);
    } else {
        for (std::int64_t axis : axes) {
            if (axis < 0) {
                axis += static_cast<std::int64_t>(x.shape.size());
            }
            if (axis < 0 || axis >= static_cast<std::int64_t>(x.shape.size())) {
                throw std::runtime_error("Reduce operator received an invalid axis");
            }
            reduce_axis[static_cast<std::size_t>(axis)] = true;
        }
    }
    Tensor out;
    std::vector<int> output_dimension_for_input(x.shape.size(), -1);
    for (std::size_t dim = 0; dim < x.shape.size(); ++dim) {
        if (reduce_axis[dim]) {
            if (keep_dims) {
                output_dimension_for_input[dim] = static_cast<int>(out.shape.size());
                out.shape.push_back(1);
            }
        } else {
            output_dimension_for_input[dim] = static_cast<int>(out.shape.size());
            out.shape.push_back(x.shape[dim]);
        }
    }
    const std::size_t output_elements = static_cast<std::size_t>(productU64(out.shape));
    const bool is_max = op == "ReduceMax";
    const bool is_min = op == "ReduceMin";
    out.data.assign(output_elements,
                    is_max ? -std::numeric_limits<float>::infinity()
                           : (is_min ? std::numeric_limits<float>::infinity() : 0.0f));
    std::vector<std::uint64_t> counts(output_elements, 0);
    for (std::size_t linear = 0; linear < x.data.size(); ++linear) {
        const std::vector<std::int64_t> input_index =
            unravel(static_cast<std::int64_t>(linear), x.shape);
        std::vector<std::int64_t> output_index(out.shape.size(), 0);
        for (std::size_t dim = 0; dim < x.shape.size(); ++dim) {
            const int output_dim = output_dimension_for_input[dim];
            if (output_dim >= 0 && !reduce_axis[dim]) {
                output_index[static_cast<std::size_t>(output_dim)] = input_index[dim];
            }
        }
        const std::size_t output_linear =
            static_cast<std::size_t>(offsetOf(out.shape, output_index));
        const float value = x.data[linear];
        if (is_max) {
            out.data[output_linear] = std::max(out.data[output_linear], value);
        } else if (is_min) {
            out.data[output_linear] = std::min(out.data[output_linear], value);
        } else if (op == "ReduceL1") {
            out.data[output_linear] += std::fabs(value);
        } else if (op == "ReduceL2") {
            out.data[output_linear] += value * value;
        } else {
            out.data[output_linear] += value;
        }
        ++counts[output_linear];
    }
    for (std::size_t index = 0; index < out.data.size(); ++index) {
        if (op == "ReduceMean") {
            out.data[index] /= static_cast<float>(std::max<std::uint64_t>(1, counts[index]));
        } else if (op == "ReduceL2") {
            out.data[index] = std::sqrt(out.data[index]);
        }
    }
    return out;
}

Tensor transpose2DIfNeeded(const Tensor& t, bool trans) {
    if (!trans) {
        return t;
    }
    if (t.shape.size() != 2) {
        throw std::runtime_error("Gemm transpose only supports 2D tensors");
    }
    Tensor out;
    out.integer_semantics = t.integer_semantics;
    out.shape = {t.shape[1], t.shape[0]};
    out.data.assign(t.data.size(), 0.0f);
    for (std::int64_t i = 0; i < t.shape[0]; ++i) {
        for (std::int64_t j = 0; j < t.shape[1]; ++j) {
            out.data[static_cast<std::size_t>(j * t.shape[0] + i)] =
                t.data[static_cast<std::size_t>(i * t.shape[1] + j)];
        }
    }
    return out;
}

Tensor softmax(const Tensor& x, std::int64_t axis) {
    Tensor out = x;
    const auto shape = normalizeAxisShape(x.shape);
    const std::int64_t rank = static_cast<std::int64_t>(shape.size());
    if (axis < 0) {
        axis += rank;
    }
    axis = std::max<std::int64_t>(0, std::min<std::int64_t>(rank - 1, axis));
    std::int64_t outer = 1;
    for (std::int64_t i = 0; i < axis; ++i) {
        outer *= shape[static_cast<std::size_t>(i)];
    }
    const std::int64_t dim = shape[static_cast<std::size_t>(axis)];
    std::int64_t inner = 1;
    for (std::int64_t i = axis + 1; i < rank; ++i) {
        inner *= shape[static_cast<std::size_t>(i)];
    }
    for (std::int64_t o = 0; o < outer; ++o) {
        for (std::int64_t in = 0; in < inner; ++in) {
            float max_v = -std::numeric_limits<float>::infinity();
            for (std::int64_t d = 0; d < dim; ++d) {
                const std::size_t idx = static_cast<std::size_t>((o * dim + d) * inner + in);
                max_v = std::max(max_v, x.data[idx]);
            }
            float denom = 0.0f;
            for (std::int64_t d = 0; d < dim; ++d) {
                const std::size_t idx = static_cast<std::size_t>((o * dim + d) * inner + in);
                out.data[idx] = std::exp(x.data[idx] - max_v);
                denom += out.data[idx];
            }
            for (std::int64_t d = 0; d < dim; ++d) {
                const std::size_t idx = static_cast<std::size_t>((o * dim + d) * inner + in);
                out.data[idx] = denom == 0.0f ? 0.0f : out.data[idx] / denom;
            }
        }
    }
    return out;
}

Tensor rmsNormalization(const Tensor& x,
                        const Tensor& scale,
                        float epsilon,
                        std::int64_t axis) {
    const std::vector<std::int64_t> shape = normalizeAxisShape(x.shape);
    const std::int64_t rank = static_cast<std::int64_t>(shape.size());
    if (axis < 0) {
        axis += rank;
    }
    if (axis < 0 || axis >= rank) {
        throw std::runtime_error("RMSNormalization received an invalid axis");
    }
    std::size_t outer = 1;
    std::size_t normalized = 1;
    for (std::int64_t dimension = 0; dimension < rank; ++dimension) {
        const std::size_t extent = static_cast<std::size_t>(shape[static_cast<std::size_t>(dimension)]);
        if (dimension < axis) {
            outer *= extent;
        } else {
            normalized *= extent;
        }
    }
    if (scale.data.empty() || (scale.data.size() != 1 && scale.data.size() != normalized)) {
        throw std::runtime_error("RMSNormalization scale must be scalar or match normalized dimensions");
    }
    Tensor out = x;
    for (std::size_t group = 0; group < outer; ++group) {
        const std::size_t base = group * normalized;
        float square_sum = 0.0f;
        for (std::size_t index = 0; index < normalized; ++index) {
            const float value = x.data[base + index];
            square_sum += value * value;
        }
        const float inverse_rms = 1.0f /
            std::sqrt(square_sum / static_cast<float>(normalized) + std::max(0.0f, epsilon));
        for (std::size_t index = 0; index < normalized; ++index) {
            const float scale_value = scale.data.size() == 1 ? scale.data.front() : scale.data[index];
            out.data[base + index] = x.data[base + index] * inverse_rms * scale_value;
        }
    }
    return out;
}

Tensor layerNormalization(const Tensor& x,
                          const Tensor& scale,
                          const Tensor* bias,
                          float epsilon,
                          std::int64_t axis) {
    const std::vector<std::int64_t> shape = normalizeAxisShape(x.shape);
    const std::int64_t rank = static_cast<std::int64_t>(shape.size());
    if (axis < 0) {
        axis += rank;
    }
    if (axis < 0 || axis >= rank) {
        throw std::runtime_error("LayerNormalization received an invalid axis");
    }
    std::size_t outer = 1;
    std::size_t normalized = 1;
    for (std::int64_t dimension = 0; dimension < rank; ++dimension) {
        const std::size_t extent = static_cast<std::size_t>(shape[static_cast<std::size_t>(dimension)]);
        if (dimension < axis) {
            outer *= extent;
        } else {
            normalized *= extent;
        }
    }
    const auto validParameter = [normalized](const Tensor& parameter) {
        return parameter.data.size() == 1 || parameter.data.size() == normalized;
    };
    if (!validParameter(scale) || (bias != nullptr && !validParameter(*bias))) {
        throw std::runtime_error("LayerNormalization scale/bias must be scalar or match normalized dimensions");
    }
    Tensor out = x;
    for (std::size_t group = 0; group < outer; ++group) {
        const std::size_t base = group * normalized;
        float mean = 0.0f;
        for (std::size_t index = 0; index < normalized; ++index) {
            mean += x.data[base + index];
        }
        mean /= static_cast<float>(normalized);
        float variance = 0.0f;
        for (std::size_t index = 0; index < normalized; ++index) {
            const float difference = x.data[base + index] - mean;
            variance += difference * difference;
        }
        const float inverse_std = 1.0f /
            std::sqrt(variance / static_cast<float>(normalized) + std::max(0.0f, epsilon));
        for (std::size_t index = 0; index < normalized; ++index) {
            const float scale_value = scale.data.size() == 1 ? scale.data.front() : scale.data[index];
            const float bias_value = bias == nullptr ? 0.0f :
                (bias->data.size() == 1 ? bias->data.front() : bias->data[index]);
            out.data[base + index] = (x.data[base + index] - mean) * inverse_std *
                                     scale_value + bias_value;
        }
    }
    return out;
}

Tensor reshapeTensor(const Tensor& x, const Tensor& shape_tensor) {
    std::vector<std::int64_t> new_shape;
    new_shape.reserve(shape_tensor.data.size());
    std::int64_t infer_idx = -1;
    std::int64_t known = 1;
    for (std::size_t i = 0; i < shape_tensor.data.size(); ++i) {
        std::int64_t dim = static_cast<std::int64_t>(std::llround(shape_tensor.data[i]));
        if (dim == 0 && i < x.shape.size()) {
            dim = x.shape[i];
        }
        if (dim == -1) {
            infer_idx = static_cast<std::int64_t>(i);
            dim = 1;
        }
        dim = std::max<std::int64_t>(1, dim);
        new_shape.push_back(dim);
        known *= dim;
    }
    if (infer_idx >= 0) {
        const std::int64_t total = static_cast<std::int64_t>(std::max<std::size_t>(1, x.data.size()));
        new_shape[static_cast<std::size_t>(infer_idx)] = std::max<std::int64_t>(1, total / std::max<std::int64_t>(1, known));
    }
    Tensor out = x;
    out.shape = new_shape.empty() ? std::vector<std::int64_t>{static_cast<std::int64_t>(x.data.size())} : new_shape;
    out.data.resize(static_cast<std::size_t>(productU64(out.shape)), 0.0f);
    return out;
}

Tensor flattenTensor(const Tensor& x, std::int64_t axis) {
    const std::int64_t rank = static_cast<std::int64_t>(x.shape.size());
    if (axis < 0) {
        axis += rank;
    }
    axis = std::max<std::int64_t>(0, std::min<std::int64_t>(rank, axis));
    std::int64_t d0 = 1;
    for (std::int64_t i = 0; i < axis; ++i) {
        d0 *= x.shape[static_cast<std::size_t>(i)];
    }
    Tensor out = x;
    out.shape = {d0, static_cast<std::int64_t>(x.data.size() / std::max<std::int64_t>(1, d0))};
    return out;
}

Tensor transposeTensor(const Tensor& x, const std::vector<std::int64_t>& perm_attr) {
    const std::size_t rank = x.shape.size();
    std::vector<std::int64_t> perm = perm_attr;
    if (perm.empty()) {
        perm.resize(rank);
        std::iota(perm.begin(), perm.end(), 0);
        std::reverse(perm.begin(), perm.end());
    }
    if (perm.size() != rank) {
        throw std::runtime_error("Transpose perm rank mismatch");
    }
    Tensor out;
    out.integer_semantics = x.integer_semantics;
    out.shape.resize(rank);
    for (std::size_t i = 0; i < rank; ++i) {
        out.shape[i] = x.shape[static_cast<std::size_t>(perm[i])];
    }
    out.data.assign(x.data.size(), 0.0f);
    for (std::size_t linear = 0; linear < out.data.size(); ++linear) {
        const auto out_idx = unravel(static_cast<std::int64_t>(linear), out.shape);
        std::vector<std::int64_t> in_idx(rank, 0);
        for (std::size_t i = 0; i < rank; ++i) {
            in_idx[static_cast<std::size_t>(perm[i])] = out_idx[i];
        }
        out.data[linear] = x.data[static_cast<std::size_t>(offsetOf(x.shape, in_idx))];
    }
    return out;
}

Tensor concatTensors(const std::vector<Tensor>& inputs, std::int64_t axis) {
    if (inputs.empty()) {
        return {};
    }
    Tensor out;
    out.integer_semantics = std::all_of(inputs.begin(), inputs.end(),
                                        [](const Tensor& t) { return t.integer_semantics; });
    out.shape = inputs[0].shape;
    const std::int64_t rank = static_cast<std::int64_t>(out.shape.size());
    if (axis < 0) {
        axis += rank;
    }
    axis = std::max<std::int64_t>(0, std::min<std::int64_t>(rank - 1, axis));
    out.shape[static_cast<std::size_t>(axis)] = 0;
    for (const auto& t : inputs) {
        out.shape[static_cast<std::size_t>(axis)] += t.shape[static_cast<std::size_t>(axis)];
    }
    out.data.assign(static_cast<std::size_t>(productU64(out.shape)), 0.0f);
    std::int64_t outer = 1;
    for (std::int64_t i = 0; i < axis; ++i) {
        outer *= out.shape[static_cast<std::size_t>(i)];
    }
    std::int64_t inner = 1;
    for (std::int64_t i = axis + 1; i < rank; ++i) {
        inner *= out.shape[static_cast<std::size_t>(i)];
    }
    std::int64_t axis_cursor = 0;
    for (const auto& t : inputs) {
        const std::int64_t axis_dim = t.shape[static_cast<std::size_t>(axis)];
        for (std::int64_t o = 0; o < outer; ++o) {
            const std::size_t dst = static_cast<std::size_t>((o * out.shape[static_cast<std::size_t>(axis)] + axis_cursor) * inner);
            const std::size_t src = static_cast<std::size_t>(o * axis_dim * inner);
            const std::size_t cnt = static_cast<std::size_t>(axis_dim * inner);
            std::copy(t.data.begin() + src, t.data.begin() + src + cnt, out.data.begin() + dst);
        }
        axis_cursor += axis_dim;
    }
    return out;
}

Tensor conv2D(const Tensor& x,
              const Tensor& w,
              const Tensor* bias,
              const Node& node,
              const RuntimeTopology& topology,
              std::uint64_t& ops,
              TensorDType accumulator_dtype = TensorDType::kFp32) {
    if (x.shape.size() != 4 || w.shape.size() != 4) {
        throw std::runtime_error("Conv currently expects NCHW input and OIHW weight");
    }
    const std::int64_t n = x.shape[0];
    const std::int64_t ic = x.shape[1];
    const std::int64_t ih = x.shape[2];
    const std::int64_t iw = x.shape[3];
    const std::int64_t oc = w.shape[0];
    const std::int64_t kh = w.shape[2];
    const std::int64_t kw = w.shape[3];
    std::vector<std::int64_t> strides = {1, 1};
    std::vector<std::int64_t> pads = {0, 0, 0, 0};
    auto it = node.ints_attrs.find("strides");
    if (it != node.ints_attrs.end() && it->second.size() >= 2) {
        strides = it->second;
    }
    it = node.ints_attrs.find("pads");
    if (it != node.ints_attrs.end() && it->second.size() >= 4) {
        pads = it->second;
    }
    const std::int64_t oh = (ih + pads[0] + pads[2] - kh) / std::max<std::int64_t>(1, strides[0]) + 1;
    const std::int64_t ow = (iw + pads[1] + pads[3] - kw) / std::max<std::int64_t>(1, strides[1]) + 1;
    Tensor out;
    out.shape = {n, oc, std::max<std::int64_t>(1, oh), std::max<std::int64_t>(1, ow)};
    out.data.assign(static_cast<std::size_t>(productU64(out.shape)), 0.0f);
    const std::int64_t work = n * oc * out.shape[2] * out.shape[3];
    const std::uint64_t work_bytes =
        static_cast<std::uint64_t>(std::max<std::int64_t>(1, x.data.size() + w.data.size() + out.data.size())) *
        sizeof(float);
    const std::vector<WorkShard> shards = buildLinearSchedule(work, work_bytes, topology);
    for (const auto& shard : shards) {
        for (std::int64_t linear = shard.begin; linear < shard.end; ++linear) {
            std::int64_t tmp = linear;
            const std::int64_t ow_i = tmp % out.shape[3];
            tmp /= out.shape[3];
            const std::int64_t oh_i = tmp % out.shape[2];
            tmp /= out.shape[2];
            const std::int64_t oc_i = tmp % oc;
            const std::int64_t n_i = tmp / oc;
            float sum = bias && !bias->data.empty() ? bias->data[static_cast<std::size_t>(oc_i % bias->data.size())] : 0.0f;
            for (std::int64_t ic_i = 0; ic_i < ic; ++ic_i) {
                for (std::int64_t kh_i = 0; kh_i < kh; ++kh_i) {
                    for (std::int64_t kw_i = 0; kw_i < kw; ++kw_i) {
                        const std::int64_t ih_i = oh_i * strides[0] + kh_i - pads[0];
                        const std::int64_t iw_i = ow_i * strides[1] + kw_i - pads[1];
                        if (ih_i < 0 || iw_i < 0 || ih_i >= ih || iw_i >= iw) {
                            continue;
                        }
                        const std::size_t xi = static_cast<std::size_t>(((n_i * ic + ic_i) * ih + ih_i) * iw + iw_i);
                        const std::size_t wi = static_cast<std::size_t>(((oc_i * ic + ic_i) * kh + kh_i) * kw + kw_i);
                        sum += x.data[xi] * w.data[wi];
                        sum = convertFloatForTensorDType(sum, accumulator_dtype);
                    }
                }
            }
            out.data[static_cast<std::size_t>(linear)] = sum;
        }
    }
    ops = 2ULL * static_cast<std::uint64_t>(work) * static_cast<std::uint64_t>(ic * kh * kw);
    return out;
}

Tensor requireTensor(const std::map<std::string, Tensor>& tensors, const std::string& name) {
    auto it = tensors.find(name);
    if (it == tensors.end()) {
        throw std::runtime_error("missing tensor: " + name);
    }
    return it->second;
}

std::uint64_t tensorLogicalBytes(const Tensor& t, std::uint64_t element_bytes) {
    return productU64(t.shape) * std::max<std::uint64_t>(1, element_bytes);
}

std::uint64_t estimateShardMemoryCycles(const ShardActivity& activity,
                                        const NPUConfig& cfg,
                                        std::uint64_t dram_cycles) {
    const std::uint64_t spm_cycles =
        ceilDiv(activity.spm_read_bytes + activity.spm_write_bytes,
                std::max<std::uint64_t>(1, cfg.sram_bandwidth_bytes_per_cycle));
    const std::uint64_t spill_cycles =
        ceilDiv(activity.spm_miss_bytes, std::max<std::uint64_t>(1, cfg.memory_unit_bytes)) *
        cfg.sram_miss_penalty_cycles;
    return spm_cycles + spill_cycles + dram_cycles;
}

double estimateArrayUtilization(std::int64_t tile_m,
                                std::int64_t tile_n,
                                const NPUConfig& cfg) {
    const std::int64_t rows = std::max(1, cfg.mac_array_rows);
    const std::int64_t cols = std::max(1, cfg.mac_array_cols);
    const std::uint64_t slots =
        ceilDiv(static_cast<std::uint64_t>(std::max<std::int64_t>(1, tile_m)),
                static_cast<std::uint64_t>(rows)) *
        static_cast<std::uint64_t>(rows) *
        ceilDiv(static_cast<std::uint64_t>(std::max<std::int64_t>(1, tile_n)),
                static_cast<std::uint64_t>(cols)) *
        static_cast<std::uint64_t>(cols);
    const double useful = static_cast<double>(std::max<std::int64_t>(1, tile_m) *
                                             std::max<std::int64_t>(1, tile_n));
    return std::max(0.05, std::min(1.0, useful / static_cast<double>(std::max<std::uint64_t>(1, slots))));
}

std::uint64_t matmulTileFootprint(std::int64_t tm,
                                  std::int64_t tn,
                                  std::int64_t tk,
                                  const NPUConfig& cfg) {
    return static_cast<std::uint64_t>(tm) * static_cast<std::uint64_t>(tk) *
               std::max<std::uint64_t>(1, cfg.activation_bytes) +
           static_cast<std::uint64_t>(tk) * static_cast<std::uint64_t>(tn) *
               std::max<std::uint64_t>(1, cfg.weight_bytes) +
           static_cast<std::uint64_t>(tm) * static_cast<std::uint64_t>(tn) *
               (std::max<std::uint64_t>(1, cfg.accumulator_bytes) +
                std::max<std::uint64_t>(1, cfg.output_bytes));
}

void chooseMatMulTile(const NPUConfig& cfg,
                      const MacProfile& mac,
                      std::int64_t rows,
                      std::int64_t k,
                      std::int64_t n,
                      std::int64_t& tm,
                      std::int64_t& tn,
                      std::int64_t& tk) {
    tm = cfg.tile_m > 0 ? cfg.tile_m : std::max(1, cfg.mac_array_rows * 8);
    tn = cfg.tile_n > 0 ? cfg.tile_n : std::max(1, cfg.mac_array_cols * 8);
    tk = cfg.tile_k > 0 ? cfg.tile_k : 64;
    tm = std::max<std::int64_t>(1, std::min(tm, std::max<std::int64_t>(1, rows)));
    tn = std::max<std::int64_t>(1, std::min(tn, std::max<std::int64_t>(1, n)));
    tk = std::max<std::int64_t>(1, std::min(tk, std::max<std::int64_t>(1, k)));

    const std::uint64_t target_spm = std::max<std::uint64_t>(1, mac.sram_bytes);
    while (matmulTileFootprint(tm, tn, tk, cfg) > target_spm && (tm > 1 || tn > 1 || tk > 1)) {
        if (tn >= tm && tn > 1) {
            tn = std::max<std::int64_t>(1, tn / 2);
        } else if (tm > 1) {
            tm = std::max<std::int64_t>(1, tm / 2);
        } else if (tk > 1) {
            tk = std::max<std::int64_t>(1, tk / 2);
        }
    }
}

OpActivity buildGenericActivity(const Tensor& out,
                                std::uint64_t ops,
                                const NPUConfig& cfg,
                                const RuntimeTopology& topology) {
    OpActivity activity;
    activity.work_items =
        std::max<std::uint64_t>(1, static_cast<std::uint64_t>(out.elements()));
    activity.ops = ops;
    activity.bytes = tensorLogicalBytes(out, cfg.output_bytes);
    activity.shards =
        buildLinearSchedule(static_cast<std::int64_t>(activity.work_items),
                            activity.bytes,
                            topology);
    activity.shard_activity.reserve(activity.shards.size());

    std::uint64_t assigned_bytes = 0;
    std::uint64_t assigned_ops = 0;
    for (std::size_t i = 0; i < activity.shards.size(); ++i) {
        const WorkShard& shard = activity.shards[i];
        const std::uint64_t span =
            static_cast<std::uint64_t>(std::max<std::int64_t>(1, shard.end - shard.begin));
        const bool last = i + 1 == activity.shards.size();
        ShardActivity local;
        local.bytes = last ? activity.bytes - assigned_bytes
                           : (activity.bytes * span) / activity.work_items;
        assigned_bytes += local.bytes;
        local.ops = ops == 0 ? 0
                             : (last ? ops - assigned_ops
                                     : (ops * span) / activity.work_items);
        assigned_ops += local.ops;
        local.input_read_bytes = local.bytes;
        local.output_write_bytes = local.bytes;
        local.spm_read_bytes = local.input_read_bytes;
        local.spm_write_bytes = local.output_write_bytes;
        const MacProfile& mac = topology.macs[static_cast<std::size_t>(shard.mac_id)];
        const std::uint64_t working_set = local.spm_read_bytes + local.spm_write_bytes;
        local.spm_miss_bytes = working_set > mac.sram_bytes ? working_set - mac.sram_bytes : 0;
        local.ddr_read_bytes = local.input_read_bytes;
        local.ddr_write_bytes = local.output_write_bytes;
        local.tile_count = 1;
        local.array_utilization = 1.0;
        activity.shard_activity.push_back(local);
    }
    return activity;
}

OpActivity buildMatMulActivity(std::int64_t m,
                               std::int64_t k,
                               std::int64_t n,
                               const NPUConfig& cfg,
                               const RuntimeTopology& topology) {
    OpActivity activity;
    activity.work_items = static_cast<std::uint64_t>(std::max<std::int64_t>(1, m));
    activity.ops = 2ULL * static_cast<std::uint64_t>(m) * static_cast<std::uint64_t>(k) *
                   static_cast<std::uint64_t>(n);
    const std::uint64_t logical_bytes =
        static_cast<std::uint64_t>(m) * static_cast<std::uint64_t>(k) *
            std::max<std::uint64_t>(1, cfg.activation_bytes) +
        static_cast<std::uint64_t>(k) * static_cast<std::uint64_t>(n) *
            std::max<std::uint64_t>(1, cfg.weight_bytes) +
        static_cast<std::uint64_t>(m) * static_cast<std::uint64_t>(n) *
            std::max<std::uint64_t>(1, cfg.output_bytes);
    activity.shards = buildLinearSchedule(m, logical_bytes, topology);
    activity.shard_activity.reserve(activity.shards.size());

    for (const WorkShard& shard : activity.shards) {
        const MacProfile& mac = topology.macs[static_cast<std::size_t>(shard.mac_id)];
        const std::int64_t local_m = std::max<std::int64_t>(0, shard.end - shard.begin);
        std::int64_t tm = 1;
        std::int64_t tn = 1;
        std::int64_t tk = 1;
        chooseMatMulTile(cfg, mac, local_m, k, n, tm, tn, tk);

        ShardActivity local;
        local.ops = 2ULL * static_cast<std::uint64_t>(local_m) *
                    static_cast<std::uint64_t>(k) * static_cast<std::uint64_t>(n);
        double utilization_sum = 0.0;

        for (std::int64_t mi = 0; mi < local_m; mi += tm) {
            const std::int64_t mt = std::min<std::int64_t>(tm, local_m - mi);
            for (std::int64_t nj = 0; nj < n; nj += tn) {
                const std::int64_t nt = std::min<std::int64_t>(tn, n - nj);
                for (std::int64_t kk = 0; kk < k; kk += tk) {
                    const std::int64_t kt = std::min<std::int64_t>(tk, k - kk);
                    const bool first_k = kk == 0;
                    const bool last_k = kk + kt >= k;
                    const std::uint64_t a_bytes =
                        static_cast<std::uint64_t>(mt) * static_cast<std::uint64_t>(kt) *
                        std::max<std::uint64_t>(1, cfg.activation_bytes);
                    const std::uint64_t b_bytes =
                        static_cast<std::uint64_t>(kt) * static_cast<std::uint64_t>(nt) *
                        std::max<std::uint64_t>(1, cfg.weight_bytes);
                    const std::uint64_t psum_bytes =
                        static_cast<std::uint64_t>(mt) * static_cast<std::uint64_t>(nt) *
                        std::max<std::uint64_t>(1, cfg.accumulator_bytes);
                    const std::uint64_t c_bytes =
                        static_cast<std::uint64_t>(mt) * static_cast<std::uint64_t>(nt) *
                        std::max<std::uint64_t>(1, cfg.output_bytes);
                    const std::uint64_t footprint = a_bytes + b_bytes + psum_bytes + c_bytes;

                    local.input_read_bytes += a_bytes;
                    local.weight_read_bytes += b_bytes;
                    local.spm_read_bytes += a_bytes + b_bytes;
                    if (!first_k) {
                        local.psum_read_bytes += psum_bytes;
                        local.spm_read_bytes += psum_bytes;
                    }
                    if (!last_k) {
                        local.psum_write_bytes += psum_bytes;
                        local.spm_write_bytes += psum_bytes;
                    } else {
                        local.output_write_bytes += c_bytes;
                        local.spm_write_bytes += c_bytes;
                    }
                    local.ddr_read_bytes += a_bytes + b_bytes;
                    if (last_k) {
                        local.ddr_write_bytes += c_bytes;
                    }
                    local.spm_miss_bytes += footprint > mac.sram_bytes ? footprint - mac.sram_bytes : 0;
                    ++local.tile_count;
                    utilization_sum += estimateArrayUtilization(mt, nt, cfg);
                }
            }
        }
        local.bytes = local.spm_read_bytes + local.spm_write_bytes;
        local.array_utilization =
            local.tile_count == 0 ? 1.0 : utilization_sum / static_cast<double>(local.tile_count);
        activity.bytes += local.bytes;
        activity.shard_activity.push_back(local);
    }
    return activity;
}

void emitBenchForNode(std::ofstream& bench,
                      std::uint64_t start_cycle,
                      std::uint64_t desc,
                      const NPUConfig& cfg,
                      const RuntimeTopology& topology,
                      const std::vector<WorkShard>& shards,
                      const std::vector<std::uint64_t>& shard_bytes,
                      const std::vector<std::uint64_t>& shard_cycles,
                      std::uint64_t& packet_count) {
    const int controller = topology.controller_node;

    for (std::size_t i = 0; i < shards.size(); ++i) {
        const std::uint64_t flits =
            ceilDiv(std::max<std::uint64_t>(64, shard_bytes[i]), cfg.flit_payload_bytes) + 1;
        const std::uint64_t worker_end =
            start_cycle + shard_cycles[i] + cfg.pipeline_depth_cycles;
        bench << start_cycle << " " << start_cycle << " " << controller << " "
              << shards[i].node_id << " " << flits << " " << desc << "\n";
        ++packet_count;
        bench << worker_end << " " << worker_end << " " << shards[i].node_id << " "
              << controller << " " << flits << " " << desc << "\n";
        ++packet_count;
    }
}

IntraDelayProfile loadRunDelayProfile(const NPUConfig& config,
                                      const std::string& delay_profile_path) {
    const IntraDelayProfile delay_profile =
        config.intra_delay_enable ? loadIntraDelayProfile(delay_profile_path) : IntraDelayProfile{};
    if (config.intra_delay_enable) {
        if (!delay_profile.loaded) {
            throw std::runtime_error(
                "NPU intra delay is enabled but the delay profile cannot be opened: " +
                delay_profile_path +
                ". Run a no-delay calibration and PopNet profile generation first, "
                "or disable intra delay for calibration.");
        }
        if (delay_profile.task_dst_delay.empty()) {
            throw std::runtime_error(
                "NPU intra delay is enabled but the delay profile has no TASK records: " +
                delay_profile_path);
        }
    }
    return delay_profile;
}

void accountExecutedOp(std::ofstream& bench,
                       RunResult& result,
                       std::uint64_t& cycle,
                       const NPUConfig& config,
                       const RuntimeTopology& topology,
                       const IntraDelayProfile& delay_profile,
                       ExternalMemoryAccounting& external_memory,
                       std::uint64_t desc,
                       const std::string& name,
                       const std::string& op_type,
                       const Tensor& out,
                       std::uint64_t ops,
                       const OpActivity* op_activity) {
    const OpActivity fallback_activity = op_activity == nullptr
                                             ? buildGenericActivity(out, ops, config, topology)
                                             : OpActivity{};
    const OpActivity& activity =
        op_activity == nullptr ? fallback_activity : *op_activity;
    const std::vector<WorkShard>& shards = activity.shards;
    std::vector<std::uint64_t> shard_bytes;
    std::vector<std::uint64_t> shard_cycles;
    shard_bytes.reserve(shards.size());
    shard_cycles.reserve(shards.size());
    std::uint64_t compute_cycles = 0;
    std::uint64_t memory_cycles = 0;
    std::uint64_t core = 1;
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
    double utilization_weighted = 0.0;
    double utilization_weight = 0.0;
    std::vector<MacUnitReport> mac_units;
    mac_units.reserve(shards.size());
    for (std::size_t shard_index = 0; shard_index < shards.size(); ++shard_index) {
        const auto& shard = shards[shard_index];
        ShardActivity local_activity =
            shard_index < activity.shard_activity.size() ? activity.shard_activity[shard_index]
                                                         : ShardActivity{};
        const MacProfile& mac = topology.macs[static_cast<std::size_t>(shard.mac_id)];
        const double util = std::max(0.05, std::min(1.0, local_activity.array_utilization));
        const std::uint64_t effective_ops_per_cycle =
            std::max<std::uint64_t>(
                1,
                static_cast<std::uint64_t>(
                    std::floor(static_cast<double>(std::max<std::uint64_t>(1, mac.ops_per_cycle)) *
                               util)));
        const std::uint64_t local_compute =
            local_activity.ops == 0 ? 0 : ceilDiv(local_activity.ops, effective_ops_per_cycle);
        const ExternalAccessStats ext_read =
            external_memory.access(false, local_activity.ddr_read_bytes);
        const ExternalAccessStats ext_write =
            external_memory.access(true, local_activity.ddr_write_bytes);
        local_activity.dram_read_transactions = ext_read.read_transactions;
        local_activity.dram_write_transactions = ext_write.write_transactions;
        local_activity.dram_cycles = ext_read.cycles + ext_write.cycles;
        const std::uint64_t local_memory =
            estimateShardMemoryCycles(local_activity, config, local_activity.dram_cycles);

        spm_read_bytes += local_activity.spm_read_bytes;
        spm_write_bytes += local_activity.spm_write_bytes;
        spm_read_accesses += ceilDiv(local_activity.spm_read_bytes, kSpmAccessBytes);
        spm_write_accesses += ceilDiv(local_activity.spm_write_bytes, kSpmAccessBytes);
        spm_miss_accesses += ceilDiv(local_activity.spm_miss_bytes, kSpmAccessBytes);
        input_read_bytes += local_activity.input_read_bytes;
        weight_read_bytes += local_activity.weight_read_bytes;
        psum_read_bytes += local_activity.psum_read_bytes;
        psum_write_bytes += local_activity.psum_write_bytes;
        output_write_bytes += local_activity.output_write_bytes;
        ddr_read_bytes += local_activity.ddr_read_bytes;
        ddr_write_bytes += local_activity.ddr_write_bytes;
        dram_read_transactions += local_activity.dram_read_transactions;
        dram_write_transactions += local_activity.dram_write_transactions;
        dram_cycles += local_activity.dram_cycles;
        tile_count += local_activity.tile_count;
        const double util_w = static_cast<double>(std::max<std::uint64_t>(1, local_activity.ops));
        utilization_weighted += util * util_w;
        utilization_weight += util_w;

        const std::uint64_t local_core =
            config.compute_memory_mode == "max"
                ? std::max(local_compute, local_memory)
                : local_compute + local_memory;
        MacUnitReport unit;
        unit.mac_id = mac.mac_id;
        unit.node_id = mac.node_id;
        unit.ops = local_activity.ops;
        unit.bytes = local_activity.bytes;
        unit.compute_cycles = local_compute;
        unit.memory_cycles = local_memory;
        unit.total_cycles = std::max<std::uint64_t>(1, local_core + config.pipeline_depth_cycles);
        unit.spm_read_accesses = ceilDiv(local_activity.spm_read_bytes, kSpmAccessBytes);
        unit.spm_write_accesses = ceilDiv(local_activity.spm_write_bytes, kSpmAccessBytes);
        unit.spm_miss_accesses = ceilDiv(local_activity.spm_miss_bytes, kSpmAccessBytes);
        unit.spm_read_bytes = local_activity.spm_read_bytes;
        unit.spm_write_bytes = local_activity.spm_write_bytes;
        unit.input_read_bytes = local_activity.input_read_bytes;
        unit.weight_read_bytes = local_activity.weight_read_bytes;
        unit.psum_read_bytes = local_activity.psum_read_bytes;
        unit.psum_write_bytes = local_activity.psum_write_bytes;
        unit.output_write_bytes = local_activity.output_write_bytes;
        unit.ddr_read_bytes = local_activity.ddr_read_bytes;
        unit.ddr_write_bytes = local_activity.ddr_write_bytes;
        unit.dram_read_transactions = local_activity.dram_read_transactions;
        unit.dram_write_transactions = local_activity.dram_write_transactions;
        unit.dram_cycles = local_activity.dram_cycles;
        unit.tile_count = local_activity.tile_count;
        unit.array_utilization = util;
        mac_units.push_back(unit);
        compute_cycles = std::max(compute_cycles, local_compute);
        memory_cycles = std::max(memory_cycles, local_memory);
        core = std::max(core, local_core);
        shard_bytes.push_back(local_activity.bytes);
        shard_cycles.push_back(std::max<std::uint64_t>(1, local_core));
    }
    std::uint64_t injected = 0;
    const auto delay_it = delay_profile.task_dst_delay.find(desc);
    if (delay_it != delay_profile.task_dst_delay.end()) {
        injected = static_cast<std::uint64_t>(
            std::llround(static_cast<double>(delay_it->second) *
                         std::max(0.0, config.intra_delay_scale)));
    } else if (config.intra_delay_enable) {
        std::ostringstream oss;
        oss << "NPU intra delay profile is missing TASK " << desc
            << " for task '" << name << "' (" << op_type << ")";
        throw std::runtime_error(oss.str());
    }
    const std::uint64_t base_total =
        std::max<std::uint64_t>(1, core + config.pipeline_depth_cycles);
    const std::uint64_t total = std::max<std::uint64_t>(1, base_total + injected);
    const std::uint64_t start_cycle = cycle;
    cycle += total;

    emitBenchForNode(bench,
                     start_cycle,
                     desc,
                     config,
                     topology,
                     shards,
                     shard_bytes,
                     shard_cycles,
                     result.emitted_packets);

    NodeReport nr;
    nr.name = name;
    nr.op_type = op_type;
    nr.ops = activity.ops;
    nr.bytes = activity.bytes;
    nr.compute_cycles = compute_cycles;
    nr.memory_cycles = memory_cycles;
    nr.injected_intra_cycles = injected;
    nr.total_cycles = total;
    nr.spm_read_accesses = spm_read_accesses;
    nr.spm_write_accesses = spm_write_accesses;
    nr.spm_miss_accesses = spm_miss_accesses;
    nr.spm_read_bytes = spm_read_bytes;
    nr.spm_write_bytes = spm_write_bytes;
    nr.input_read_bytes = input_read_bytes;
    nr.weight_read_bytes = weight_read_bytes;
    nr.psum_read_bytes = psum_read_bytes;
    nr.psum_write_bytes = psum_write_bytes;
    nr.output_write_bytes = output_write_bytes;
    nr.ddr_read_bytes = ddr_read_bytes;
    nr.ddr_write_bytes = ddr_write_bytes;
    nr.dram_read_transactions = dram_read_transactions;
    nr.dram_write_transactions = dram_write_transactions;
    nr.dram_cycles = dram_cycles;
    nr.tile_count = tile_count;
    nr.array_utilization =
        utilization_weight > 0.0 ? utilization_weighted / utilization_weight : 1.0;
    nr.active_macs = static_cast<int>(topology.macs.size());
    nr.mac_units = std::move(mac_units);
    result.node_reports.push_back(nr);
    result.compute_cycles += total - injected;
    result.injected_intra_cycles += injected;
    result.ddr_read_bytes += ddr_read_bytes;
    result.ddr_write_bytes += ddr_write_bytes;
    result.dram_read_transactions += dram_read_transactions;
    result.dram_write_transactions += dram_write_transactions;
    result.dram_cycles += dram_cycles;
}

Tensor executeNode(const Node& node,
                   std::map<std::string, Tensor>& tensors,
                   const RuntimeTopology& topology,
                   std::uint64_t& ops,
                   TensorDType accumulator_dtype = TensorDType::kFp32) {
    ops = 0;
    if (node.op_type == "Constant") {
        auto it = node.tensor_attrs.find("value");
        if (it == node.tensor_attrs.end()) {
            throw std::runtime_error("Constant without tensor value");
        }
        return it->second;
    }
    std::vector<Tensor> ins;
    for (const auto& input : node.inputs) {
        if (!input.empty()) {
            ins.push_back(requireTensor(tensors, input));
        }
    }
    if (node.op_type == "MatMul") {
        if (ins.size() < 2) {
            throw std::runtime_error("MatMul expects 2 inputs");
        }
        return matmul2D(ins[0], ins[1], topology, ops, accumulator_dtype);
    }
    if (node.op_type == "Gemm") {
        if (ins.size() < 2) {
            throw std::runtime_error("Gemm expects at least 2 inputs");
        }
        const bool trans_a = node.int_attrs.count("transA") && node.int_attrs.at("transA") != 0;
        const bool trans_b = node.int_attrs.count("transB") && node.int_attrs.at("transB") != 0;
        Tensor a = transpose2DIfNeeded(ins[0], trans_a);
        Tensor b = transpose2DIfNeeded(ins[1], trans_b);
        Tensor out = matmul2D(a, b, topology, ops, accumulator_dtype);
        const float alpha = node.float_attrs.count("alpha") ? node.float_attrs.at("alpha") : 1.0f;
        const float beta = node.float_attrs.count("beta") ? node.float_attrs.at("beta") : 1.0f;
        for (float& v : out.data) {
            v *= alpha;
        }
        if (ins.size() >= 3) {
            Tensor scaled_bias = ins[2];
            for (float& v : scaled_bias.data) {
                v *= beta;
            }
            out = elementwiseBinary(out, scaled_bias, "Add");
        }
        return out;
    }
    if (node.op_type == "Conv") {
        if (ins.size() < 2) {
            throw std::runtime_error("Conv expects at least 2 inputs");
        }
        const Tensor* bias = ins.size() >= 3 ? &ins[2] : nullptr;
        return conv2D(ins[0], ins[1], bias, node, topology, ops, accumulator_dtype);
    }
    if (node.op_type == "Add" || node.op_type == "Sub" || node.op_type == "Mul" ||
        node.op_type == "Div" || node.op_type == "Pow") {
        Tensor out = elementwiseBinary(ins[0], ins[1], node.op_type);
        ops = static_cast<std::uint64_t>(out.data.size());
        return out;
    }
    if (node.op_type == "Relu" || node.op_type == "Sigmoid" || node.op_type == "Tanh" ||
        node.op_type == "Neg" || node.op_type == "Abs" || node.op_type == "Exp" ||
        node.op_type == "Log" || node.op_type == "Sqrt" || node.op_type == "Reciprocal" ||
        node.op_type == "Rsqrt" || node.op_type == "Erf" || node.op_type == "Gelu" ||
        node.op_type == "SiLU") {
        Tensor out = unary(ins[0], node.op_type);
        ops = static_cast<std::uint64_t>(out.data.size());
        return out;
    }
    if (node.op_type == "Softmax" || node.op_type == "LogSoftmax") {
        const std::int64_t axis = node.int_attrs.count("axis") ? node.int_attrs.at("axis") : -1;
        Tensor out = softmax(ins[0], axis);
        if (node.op_type == "LogSoftmax") {
            for (float& value : out.data) {
                value = std::log(std::max(value, std::numeric_limits<float>::min()));
            }
        }
        ops = 3ULL * static_cast<std::uint64_t>(out.data.size());
        return out;
    }
    if (node.op_type == "RMSNormalization") {
        if (ins.size() < 2) {
            throw std::runtime_error("RMSNormalization expects input and scale");
        }
        const float epsilon = node.float_attrs.count("epsilon") ? node.float_attrs.at("epsilon") : 1.0e-5f;
        const std::int64_t axis = node.int_attrs.count("axis") ? node.int_attrs.at("axis") : -1;
        Tensor out = rmsNormalization(ins[0], ins[1], epsilon, axis);
        ops = 3ULL * static_cast<std::uint64_t>(out.data.size());
        return out;
    }
    if (node.op_type == "LayerNormalization") {
        if (ins.size() < 2) {
            throw std::runtime_error("LayerNormalization expects input and scale");
        }
        const float epsilon = node.float_attrs.count("epsilon") ? node.float_attrs.at("epsilon") : 1.0e-5f;
        const std::int64_t axis = node.int_attrs.count("axis") ? node.int_attrs.at("axis") : -1;
        const Tensor* bias = ins.size() >= 3 ? &ins[2] : nullptr;
        Tensor out = layerNormalization(ins[0], ins[1], bias, epsilon, axis);
        ops = 4ULL * static_cast<std::uint64_t>(out.data.size());
        return out;
    }
    if (node.op_type == "ReduceMean" || node.op_type == "ReduceSum" ||
        node.op_type == "ReduceMax" || node.op_type == "ReduceMin" ||
        node.op_type == "ReduceL1" || node.op_type == "ReduceL2") {
        std::vector<std::int64_t> axes;
        bool axes_supplied = false;
        const auto axes_attribute = node.ints_attrs.find("axes");
        if (axes_attribute != node.ints_attrs.end()) {
            axes = axes_attribute->second;
            axes_supplied = true;
        } else if (ins.size() >= 2) {
            axes.reserve(ins[1].data.size());
            for (float value : ins[1].data) {
                axes.push_back(static_cast<std::int64_t>(std::llround(value)));
            }
            axes_supplied = true;
        }
        // The helper uses an empty list to denote omitted axes/reduce-all.
        // An explicit empty axes tensor is a legal ONNX no-op; preserve it by
        // returning the input alias in that uncommon case.
        if (axes_supplied && axes.empty()) {
            ops = 0;
            return ins[0];
        }
        const bool keep_dims = !node.int_attrs.count("keepdims") || node.int_attrs.at("keepdims") != 0;
        Tensor out = reduceTensor(ins[0], axes, keep_dims, node.op_type);
        ops = static_cast<std::uint64_t>(ins[0].data.size());
        return out;
    }
    if (node.op_type == "Reshape") {
        return reshapeTensor(ins[0], ins[1]);
    }
    if (node.op_type == "Flatten") {
        const std::int64_t axis = node.int_attrs.count("axis") ? node.int_attrs.at("axis") : 1;
        return flattenTensor(ins[0], axis);
    }
    if (node.op_type == "Transpose") {
        const auto it = node.ints_attrs.find("perm");
        return transposeTensor(ins[0], it == node.ints_attrs.end() ? std::vector<std::int64_t>{} : it->second);
    }
    if (node.op_type == "Concat") {
        const std::int64_t axis = node.int_attrs.count("axis") ? node.int_attrs.at("axis") : 0;
        return concatTensors(ins, axis);
    }
    if (node.op_type == "Identity" || node.op_type == "Dropout") {
        return ins[0];
    }
    throw std::runtime_error("unsupported ONNX op in NPUSim C++ runtime: " + node.op_type);
}

FunctionalOnnxResult executeOnnxFunctionally(
    const Model& model,
    const std::vector<Tensor>& external_inputs,
    const FunctionalOnnxExecutionOptions& options) {
    std::map<std::string, Tensor> tensors = model.initializers;
    // Initializers are host FP32 after protobuf decoding.  Quantize them once
    // when they become NPU-resident weights so FP16/BF16 functional results do
    // not silently retain the original FP32 coefficients.
    for (auto& initializer : tensors) {
        if (!initializer.second.integer_semantics) {
            convertFloatTensorInPlace(initializer.second.data, options.weight_dtype);
        }
    }
    std::size_t external_index = 0;
    for (const std::string& input_name : model.graph_inputs) {
        if (model.initializers.count(input_name) != 0) {
            continue;
        }
        if (external_index >= external_inputs.size()) {
            throw std::runtime_error("functional ONNX execution is missing graph input '" +
                                     input_name + "'");
        }
        const auto shape_it = model.value_shapes.find(input_name);
        if (shape_it == model.value_shapes.end()) {
            throw std::runtime_error("functional ONNX execution lacks shape for graph input '" +
                                     input_name + "'");
        }
        tensors[input_name] = normalizeExternalFunctionalInput(
            external_inputs[external_index++], shape_it->second, input_name);
        convertFloatTensorInPlace(tensors[input_name].data, options.activation_dtype);
    }
    if (external_index != external_inputs.size()) {
        throw std::runtime_error("functional ONNX execution received more inputs than the graph declares");
    }

    // The functional reference uses a one-MAC topology solely for existing
    // MatMul/Conv helpers; no simulated timing or packet is produced here.
    RuntimeTopology functional_topology;
    functional_topology.controller_node = 0;
    functional_topology.macs.push_back({0, 0, 0, 0, 0, 1});
    for (const Node& node : model.nodes) {
        std::uint64_t ignored_ops = 0;
        Tensor output = executeNode(node, tensors, functional_topology, ignored_ops,
                                    options.accumulator_dtype);
        if (options.round_each_operator && !output.integer_semantics) {
            convertFloatTensorInPlace(output.data, options.activation_dtype);
        }
        for (const std::string& output_name : node.outputs) {
            if (!output_name.empty()) {
                tensors[output_name] = output;
            }
        }
    }

    FunctionalOnnxResult result;
    std::vector<std::string> outputs = model.graph_outputs;
    if (outputs.empty() && !model.nodes.empty()) {
        outputs = model.nodes.back().outputs;
    }
    for (const std::string& output_name : outputs) {
        const auto output = tensors.find(output_name);
        if (output == tensors.end()) {
            throw std::runtime_error("functional ONNX execution did not materialize output '" +
                                     output_name + "'");
        }
        Tensor materialized_output = output->second;
        convertFloatTensorInPlace(materialized_output.data, options.output_dtype);
        result.output_tensors.push_back(std::move(materialized_output));
    }
    if (result.output_tensors.empty()) {
        throw std::runtime_error("functional ONNX execution produced no graph outputs");
    }
    result.named_tensors = std::move(tensors);
    return result;
}

}  // namespace

std::size_t Tensor::elements() const {
    return static_cast<std::size_t>(productU64(shape));
}

FunctionalOnnxResult runOnnxFunctionally(
    const std::vector<char>& model_bytes,
    const std::vector<Tensor>& external_inputs,
    const FunctionalOnnxExecutionOptions& options) {
#if defined(__GNUC__) && !defined(NPUSIM_REQUIRE_OFFICIAL_ONNX)
    if (&parseOnnxModel == nullptr) {
        throw std::runtime_error(
            "ONNX functional execution requires the official ONNX frontend; build NPUSim through CMake");
    }
#endif
    return executeOnnxFunctionally(parseOnnxModel(model_bytes), external_inputs, options);
}

NpuEventId NpuEventRecorder::append(
    NpuProgramEventKind kind,
    std::uint64_t op_desc,
    int mac_id,
    std::uint64_t address,
    std::uint64_t bytes,
    std::uint64_t ops,
    const std::vector<std::uint64_t>& wait_request_ids,
    const std::vector<NpuEventId>& dependencies) {
    if (next_id_ == 0) {
        throw std::runtime_error("NPU event recorder exhausted event identifiers");
    }
    const NpuEventId id = next_id_++;
    events_.push_back({id, op_desc, kind, mac_id, address, bytes, ops, dependencies,
                       wait_request_ids});
    return id;
}

NpuEventId NpuEventRecorder::dmaLoad(
    std::uint64_t op_desc,
    std::uint64_t address,
    std::uint64_t bytes,
    const std::vector<NpuEventId>& dependencies) {
    return append(NpuProgramEventKind::kDmaLoad,
                  op_desc,
                  -1,
                  address,
                  bytes,
                  0,
                  {},
                  dependencies);
}

NpuEventId NpuEventRecorder::dmaStore(
    std::uint64_t op_desc,
    std::uint64_t address,
    std::uint64_t bytes,
    const std::vector<NpuEventId>& dependencies) {
    return append(NpuProgramEventKind::kDmaStore,
                  op_desc,
                  -1,
                  address,
                  bytes,
                  0,
                  {},
                  dependencies);
}

NpuEventId NpuEventRecorder::macCompute(
    std::uint64_t op_desc,
    std::uint64_t ops,
    int mac_id,
    const std::vector<NpuEventId>& dependencies) {
    return append(NpuProgramEventKind::kMacCompute,
                  op_desc,
                  mac_id,
                  0,
                  0,
                  ops,
                  {},
                  dependencies);
}

NpuEventId NpuEventRecorder::vectorCompute(
    std::uint64_t op_desc,
    std::uint64_t ops,
    const std::vector<NpuEventId>& dependencies) {
    return append(NpuProgramEventKind::kVectorCompute,
                  op_desc,
                  -1,
                  0,
                  0,
                  ops,
                  {},
                  dependencies);
}

NpuEventId NpuEventRecorder::reduceCompute(
    std::uint64_t op_desc,
    std::uint64_t ops,
    const std::vector<NpuEventId>& dependencies) {
    return append(NpuProgramEventKind::kReduceCompute,
                  op_desc,
                  -1,
                  0,
                  0,
                  ops,
                  {},
                  dependencies);
}

NpuEventId NpuEventRecorder::barrier(
    std::uint64_t op_desc,
    const std::vector<NpuEventId>& dependencies) {
    return append(NpuProgramEventKind::kBarrier,
                  op_desc,
                  -1,
                  0,
                  0,
                  0,
                  {},
                  dependencies);
}

NpuEventId NpuEventRecorder::waitRequests(
    std::uint64_t op_desc,
    const std::vector<std::uint64_t>& wait_request_ids,
    const std::vector<NpuEventId>& dependencies) {
    return append(NpuProgramEventKind::kBarrier,
                  op_desc,
                  -1,
                  0,
                  0,
                  0,
                  wait_request_ids,
                  dependencies);
}

const std::vector<NpuProgramEvent>& NpuEventRecorder::events() const {
    return events_;
}

void NpuEventRecorder::clear() {
    events_.clear();
    next_id_ = 1;
}

NPUConfig loadConfig(const std::string& path) {
    NPUConfig cfg;
    const std::string text = readFileToString(path);
    if (text.empty()) {
        return cfg;
    }
    const nlohmann::json root = nlohmann::json::parse(text);
    const nlohmann::json npu = root.value("npu", nlohmann::json::object());
    const nlohmann::json timing = root.value("timing", nlohmann::json::object());
    const nlohmann::json topo = npu.value("topology", nlohmann::json::object());
    const nlohmann::json mac_array = npu.value("mac_array", nlohmann::json::object());
    const nlohmann::json tiling = npu.value("tiling", nlohmann::json::object());
    const nlohmann::json external_memory =
        root.contains("external_memory") ? root.value("external_memory", nlohmann::json::object())
                                         : npu.value("external_memory", nlohmann::json::object());

    cfg.mac_unit_count = npu.value("mac_unit_count", cfg.mac_unit_count);
    cfg.topology_mode = topo.value("mode", cfg.topology_mode);
    cfg.topology_gv_path = joinPath(dirnameOf(path), topo.value("gv_path", cfg.topology_gv_path));
    cfg.topology_node_count = topo.value("node_count", cfg.topology_node_count);
    cfg.rows = topo.value("rows", cfg.rows);
    cfg.cols = topo.value("cols", cfg.cols);
    cfg.controller_local_id = topo.value("controller_node", topo.value("controller_local_id", cfg.controller_local_id));
    if (topo.contains("mac_nodes") && topo["mac_nodes"].is_array()) {
        cfg.mac_nodes = topo["mac_nodes"].get<std::vector<int>>();
    }
    cfg.sram_per_mac_bytes = npu.value("sram_per_mac_bytes", cfg.sram_per_mac_bytes);
    cfg.activation_bytes = npu.value("activation_bytes", cfg.activation_bytes);
    cfg.weight_bytes = npu.value("weight_bytes", cfg.weight_bytes);
    cfg.accumulator_bytes = npu.value("accumulator_bytes", cfg.accumulator_bytes);
    cfg.output_bytes = npu.value("output_bytes", cfg.output_bytes);
    const auto dtypeFromConfigOrWidth = [&npu](const char* key,
                                                std::uint64_t bytes,
                                                bool& explicit_dtype) {
        explicit_dtype = npu.contains(key);
        if (npu.contains(key)) {
            return tensorDTypeFromString(npu.at(key).get<std::string>());
        }
        // Legacy configs expressed only byte widths.  Preserve their ability
        // to run while making the former implicit 2-byte choice explicit as
        // FP16.  BF16 users must write *_dtype: "bf16" because width alone
        // cannot distinguish the two formats.
        if (bytes == 4) {
            return TensorDType::kFp32;
        }
        if (bytes == 2) {
            return TensorDType::kFp16;
        }
        // Old timing-only INT8/INT16 configurations have no numerical wire
        // protocol.  Preserve them: their byte width remains authoritative
        // for timing.  An ONNX CPU/NPU wrapper must explicitly write a dtype.
        return TensorDType::kFp32;
    };
    cfg.activation_dtype = dtypeFromConfigOrWidth(
        "activation_dtype", cfg.activation_bytes, cfg.activation_dtype_explicit);
    cfg.weight_dtype = dtypeFromConfigOrWidth(
        "weight_dtype", cfg.weight_bytes, cfg.weight_dtype_explicit);
    cfg.accumulator_dtype = dtypeFromConfigOrWidth(
        "accumulator_dtype", cfg.accumulator_bytes, cfg.accumulator_dtype_explicit);
    cfg.output_dtype = dtypeFromConfigOrWidth(
        "output_dtype", cfg.output_bytes, cfg.output_dtype_explicit);
    cfg.functional_round_each_operator =
        npu.value("functional_round_each_operator", cfg.functional_round_each_operator);
    cfg.onnx_materialize_weights_to_dram =
        npu.value("onnx_materialize_weights_to_dram", cfg.onnx_materialize_weights_to_dram);
    cfg.mac_array_rows = mac_array.value("rows", npu.value("mac_array_rows", cfg.mac_array_rows));
    cfg.mac_array_cols = mac_array.value("cols", npu.value("mac_array_cols", cfg.mac_array_cols));
    cfg.tile_m = tiling.value("tile_m", npu.value("tile_m", cfg.tile_m));
    cfg.tile_n = tiling.value("tile_n", npu.value("tile_n", cfg.tile_n));
    cfg.tile_k = tiling.value("tile_k", npu.value("tile_k", cfg.tile_k));
    cfg.mac_ops_per_cycle = npu.value("mac_ops_per_cycle", cfg.mac_ops_per_cycle);
    cfg.vector_ops_per_cycle = npu.value("vector_ops_per_cycle", cfg.vector_ops_per_cycle);
    cfg.reduce_ops_per_cycle = npu.value("reduce_ops_per_cycle", cfg.reduce_ops_per_cycle);
    cfg.sram_bandwidth_bytes_per_cycle =
        npu.value("sram_bandwidth_bytes_per_cycle", cfg.sram_bandwidth_bytes_per_cycle);
    cfg.ddr_bandwidth_bytes_per_cycle =
        npu.value("ddr_bandwidth_bytes_per_cycle", cfg.ddr_bandwidth_bytes_per_cycle);
    cfg.memory_unit_bytes = npu.value("memory_unit_bytes", cfg.memory_unit_bytes);
    cfg.sram_miss_penalty_cycles = npu.value("sram_miss_penalty_cycles", cfg.sram_miss_penalty_cycles);
    cfg.pipeline_depth_cycles = npu.value("pipeline_depth_cycles", cfg.pipeline_depth_cycles);
    cfg.flit_payload_bytes = npu.value("flit_payload_bytes", cfg.flit_payload_bytes);
    cfg.intra_delay_enable = timing.value("intra_delay_enable", cfg.intra_delay_enable);
    cfg.intra_delay_scale = timing.value("intra_delay_scale", cfg.intra_delay_scale);
    cfg.compute_memory_mode = timing.value("compute_memory_mode", cfg.compute_memory_mode);
    cfg.external_memory_enable = external_memory.value("enable", cfg.external_memory_enable);
    cfg.external_memory_model = external_memory.value("model", cfg.external_memory_model);
    cfg.dram_transaction_bytes =
        external_memory.value("transaction_bytes", cfg.dram_transaction_bytes);
    cfg.dram_read_fixed_latency_cycles =
        external_memory.value("read_fixed_latency_cycles", cfg.dram_read_fixed_latency_cycles);
    cfg.dram_write_fixed_latency_cycles =
        external_memory.value("write_fixed_latency_cycles", cfg.dram_write_fixed_latency_cycles);
    cfg.dram_cycle_scale = external_memory.value("cycle_scale", cfg.dram_cycle_scale);
    cfg.dram_size_bytes = external_memory.value("size_bytes", cfg.dram_size_bytes);
    const nlohmann::json chiplet =
        external_memory.value("chiplet", nlohmann::json::object());
    cfg.dram_chiplet_x = chiplet.value("x", cfg.dram_chiplet_x);
    cfg.dram_chiplet_y = chiplet.value("y", cfg.dram_chiplet_y);
    cfg.dram_chiplet_burst_bytes =
        chiplet.value("burst_bytes", cfg.dram_chiplet_burst_bytes);
    cfg.dram_chiplet_region_bytes =
        chiplet.value("region_bytes", cfg.dram_chiplet_region_bytes);
    cfg.dram_chiplet_grid_cols =
        chiplet.value("grid_cols", cfg.dram_chiplet_grid_cols);
    cfg.mac_unit_count = std::max(1, cfg.mac_unit_count);
    cfg.rows = std::max(1, cfg.rows);
    cfg.cols = std::max(1, cfg.cols);
    cfg.activation_bytes = std::max<std::uint64_t>(1, cfg.activation_bytes);
    cfg.weight_bytes = std::max<std::uint64_t>(1, cfg.weight_bytes);
    cfg.accumulator_bytes = std::max<std::uint64_t>(1, cfg.accumulator_bytes);
    cfg.output_bytes = std::max<std::uint64_t>(1, cfg.output_bytes);
    const auto requireWidthMatchesDType = [](const char* name,
                                             std::uint64_t bytes,
                                             TensorDType dtype) {
        const std::uint64_t expected = static_cast<std::uint64_t>(tensorDTypeBytes(dtype));
        if (bytes != expected) {
            std::ostringstream oss;
            oss << "NPU config " << name << "=" << bytes
                << " conflicts with its dtype=" << tensorDTypeName(dtype)
                << " (expected " << expected << " bytes)";
            throw std::runtime_error(oss.str());
        }
    };
    if (cfg.activation_dtype_explicit) {
        requireWidthMatchesDType("activation_bytes", cfg.activation_bytes, cfg.activation_dtype);
    }
    if (cfg.weight_dtype_explicit) {
        requireWidthMatchesDType("weight_bytes", cfg.weight_bytes, cfg.weight_dtype);
    }
    if (cfg.accumulator_dtype_explicit) {
        requireWidthMatchesDType("accumulator_bytes", cfg.accumulator_bytes, cfg.accumulator_dtype);
    }
    if (cfg.output_dtype_explicit) {
        requireWidthMatchesDType("output_bytes", cfg.output_bytes, cfg.output_dtype);
    }
    cfg.mac_array_rows = std::max(1, cfg.mac_array_rows);
    cfg.mac_array_cols = std::max(1, cfg.mac_array_cols);
    cfg.tile_m = std::max(0, cfg.tile_m);
    cfg.tile_n = std::max(0, cfg.tile_n);
    cfg.tile_k = std::max(0, cfg.tile_k);
    cfg.mac_ops_per_cycle = std::max<std::uint64_t>(1, cfg.mac_ops_per_cycle);
    cfg.vector_ops_per_cycle = std::max<std::uint64_t>(1, cfg.vector_ops_per_cycle);
    cfg.reduce_ops_per_cycle = std::max<std::uint64_t>(1, cfg.reduce_ops_per_cycle);
    cfg.dram_transaction_bytes = std::max<std::uint64_t>(1, cfg.dram_transaction_bytes);
    cfg.dram_cycle_scale = std::max(0.0, cfg.dram_cycle_scale);
    cfg.dram_size_bytes = std::max<std::uint64_t>(cfg.dram_transaction_bytes, cfg.dram_size_bytes);
    if (cfg.mac_nodes.empty()) {
        throw std::runtime_error(
            "NPUSim config must explicitly provide npu.topology.mac_nodes; no default MAC-node map is used.");
    }
    if (cfg.mac_nodes.size() != static_cast<std::size_t>(cfg.mac_unit_count)) {
        std::ostringstream oss;
        oss << "invalid NPU topology: mac_nodes has " << cfg.mac_nodes.size()
            << " entries, mac_unit_count is " << cfg.mac_unit_count;
        throw std::runtime_error(oss.str());
    }
    cfg.controller_local_id = std::max(0, cfg.controller_local_id);
    cfg.topology_node_count = std::max(cfg.topology_node_count, cfg.controller_local_id + 1);
    for (int node : cfg.mac_nodes) {
        cfg.topology_node_count = std::max(cfg.topology_node_count, node + 1);
    }
    return cfg;
}

TopologyInfo describeTopology(const NPUConfig& config) {
    const RuntimeTopology runtime = buildRuntimeTopology(config);
    TopologyInfo info;
    info.node_count = runtime.node_count;
    info.controller_node = runtime.controller_node;
    info.gv_path = runtime.gv_path;
    info.macs.reserve(runtime.macs.size());
    for (const auto& mac : runtime.macs) {
        info.macs.push_back({
            mac.mac_id,
            mac.node_id,
            mac.degree,
            mac.distance_to_controller,
            mac.sram_bytes,
            mac.ops_per_cycle,
        });
    }
    return info;
}

IntraDelayProfile loadIntraDelayProfile(const std::string& path) {
    IntraDelayProfile profile;
    std::ifstream in(path);
    if (!in.is_open()) {
        return profile;
    }
    profile.loaded = true;
    std::string key;
    while (in >> key) {
        if (key == "TOTAL") {
            in >> profile.total_dst_delay;
        } else if (key == "PACKETS") {
            in >> profile.packet_count;
        } else if (key == "TASK") {
            std::uint64_t desc = 0;
            std::uint64_t dst = 0;
            std::uint64_t src = 0;
            std::uint64_t packets = 0;
            in >> desc >> dst >> src >> packets;
            if (desc != 0) {
                profile.task_dst_delay[desc] = dst;
                profile.task_src_delay[desc] = src;
            }
        } else if (key == "MAC" || key == "PE") {
            int mac = 0;
            std::uint64_t dst = 0;
            std::uint64_t src = 0;
            in >> mac >> dst >> src;
            profile.mac_dst_delay[mac] = dst;
            profile.mac_src_delay[mac] = src;
        }
        std::string rest;
        std::getline(in, rest);
    }
    if (profile.total_dst_delay == 0) {
        for (const auto& item : profile.task_dst_delay) {
            profile.total_dst_delay += item.second;
        }
    }
    if (profile.total_src_delay == 0) {
        for (const auto& item : profile.task_src_delay) {
            profile.total_src_delay += item.second;
        }
    }
    return profile;
}

std::uint64_t loadIntraDelayCycles(const std::string& path) {
    return loadIntraDelayProfile(path).total_dst_delay;
}

RunResult runModel(const std::vector<char>& model_bytes,
                   const std::vector<std::int64_t>& input0,
                   const std::vector<std::int64_t>& input1,
                   const NPUConfig& config,
                   const std::string& bench_path,
                   const std::string& delay_profile_path,
                   bool estimate_only) {
#if defined(__GNUC__) && !defined(NPUSIM_REQUIRE_OFFICIAL_ONNX)
    if (&parseOnnxModel == nullptr) {
        throw std::runtime_error(
            "ONNX execution requires the official ONNX frontend; build NPUSim through CMake");
    }
#endif
    const Model model = parseOnnxModel(model_bytes);
    const RuntimeTopology topology = buildRuntimeTopology(config);
    std::map<std::string, Tensor> tensors = model.initializers;
    std::vector<std::string> external_inputs;
    for (const auto& name : model.graph_inputs) {
        if (model.initializers.count(name) == 0) {
            external_inputs.push_back(name);
        }
    }
    if (!external_inputs.empty()) {
        tensors[external_inputs[0]] =
            tensorFromI64(input0, shapeForExternalInput(model, external_inputs[0], input0.size()));
    }
    if (external_inputs.size() >= 2) {
        tensors[external_inputs[1]] =
            tensorFromI64(input1, shapeForExternalInput(model, external_inputs[1], input1.size()));
    }

    std::ofstream bench(bench_path, std::ios::out | std::ios::trunc);
    if (!bench.is_open()) {
        throw std::runtime_error("cannot open NPU intra bench for write: " + bench_path);
    }

    RunResult result;
    const IntraDelayProfile delay_profile = loadRunDelayProfile(config, delay_profile_path);
    ExternalMemoryAccounting external_memory(config);
    std::uint64_t cycle = 0;
    for (std::size_t idx = 0; idx < model.nodes.size(); ++idx) {
        const Node& node = model.nodes[idx];
        const std::uint64_t desc = static_cast<std::uint64_t>(idx + 1);
        // Preserve a true tile plan for the ONNX MatMul path.  The previous
        // generic per-MAC fallback is useful for every supported operator,
        // but it loses individual data_ready -> MAC dependencies for MatMul.
        // Restrict this specialised path to 2-D inputs.  A batch-aware
        // MatMul planner is deliberately not inferred from the last two
        // dimensions here; higher-rank inputs keep the generic fallback until
        // their batch/dataflow semantics are modelled explicitly.
        std::vector<NpuTileEvent> specialised_tiles;
        OpActivity specialised_activity;
        const OpActivity* activity = nullptr;
        if (node.op_type == "MatMul" && node.inputs.size() >= 2 &&
            !node.inputs[0].empty() && !node.inputs[1].empty()) {
            const auto a_it = tensors.find(node.inputs[0]);
            const auto b_it = tensors.find(node.inputs[1]);
            if (a_it != tensors.end() && b_it != tensors.end() &&
                a_it->second.shape.size() == 2 && b_it->second.shape.size() == 2) {
                const std::int64_t m = a_it->second.shape[0];
                const std::int64_t k = a_it->second.shape[1];
                const std::int64_t kb = b_it->second.shape[0];
                const std::int64_t n = b_it->second.shape[1];
                if (m <= 0 || k <= 0 || kb <= 0 || n <= 0 || k != kb) {
                    throw std::runtime_error("ONNX MatMul shape mismatch");
                }
                specialised_activity = buildMatMulActivity(m, k, n, config, topology);
                activity = &specialised_activity;
                specialised_tiles = planMatMulTiles(m, k, n, config);
                for (NpuTileEvent& tile : specialised_tiles) {
                    tile.op_desc = desc;
                }
            }
        }
        std::uint64_t ops = 0;
        Tensor out = executeNode(node, tensors, topology, ops);
        accountExecutedOp(bench,
                          result,
                          cycle,
                          config,
                          topology,
                          delay_profile,
                          external_memory,
                          desc,
                          node.name,
                          node.op_type,
                          out,
                          ops,
                          activity);

        // Every operator exposes at least one schedulable descriptor per
        // active MAC.  MatMul above replaces this coarse shard view with true
        // tiles; Conv/Gemm and non-MAC operators retain the safe coarse
        // fallback until they get their own traffic planner, without changing
        // the adapter/runtime callback contract.
        const NodeReport& node_report = result.node_reports.back();
        if (!specialised_tiles.empty()) {
            std::uint64_t planned_read_bytes = 0;
            std::uint64_t planned_write_bytes = 0;
            for (const NpuTileEvent& tile : specialised_tiles) {
                planned_read_bytes += tile.ddr_read_bytes;
                planned_write_bytes += tile.ddr_write_bytes;
            }
            if (planned_read_bytes != node_report.ddr_read_bytes ||
                planned_write_bytes != node_report.ddr_write_bytes) {
                throw std::runtime_error("ONNX MatMul tile plan disagrees with runtime DDR accounting");
            }
            result.tile_events.insert(result.tile_events.end(),
                                      specialised_tiles.begin(),
                                      specialised_tiles.end());
        } else {
            std::uint64_t tile_id = 1;
            for (const MacUnitReport& unit : node_report.mac_units) {
                NpuTileEvent event;
                event.op_desc = desc;
                event.tile_id = tile_id++;
                event.mac_id = unit.mac_id;
                event.node_id = unit.node_id;
                event.ops = unit.ops;
                event.ddr_read_bytes = unit.ddr_read_bytes;
                event.ddr_write_bytes = unit.ddr_write_bytes;
                event.compute_cycles = unit.compute_cycles;
                event.local_memory_cycles = unit.memory_cycles;
                result.tile_events.push_back(event);
            }
        }

        for (const auto& output_name : node.outputs) {
            if (!output_name.empty()) {
                tensors[output_name] = out;
            }
        }
    }

    bench.close();
    result.total_cycles = cycle;
    result.end_to_end_cycles = result.total_cycles;

    if (!estimate_only) {
        std::vector<std::string> outputs = model.graph_outputs;
        if (outputs.empty() && !model.nodes.empty()) {
            outputs = model.nodes.back().outputs;
        }
        for (const auto& name : outputs) {
            auto it = tensors.find(name);
            if (it != tensors.end()) {
                result.output_tensors.push_back(it->second);
            }
        }
        if (!result.output_tensors.empty()) {
            const Tensor& primary = result.output_tensors.front();
            result.output_i64.reserve(primary.data.size());
            for (float value : primary.data) {
                result.output_i64.push_back(static_cast<std::int64_t>(std::llround(value)));
            }
        }
    }
    return result;
}

RunResult runMatMulI64(const std::vector<std::int64_t>& input0,
                       const std::vector<std::int64_t>& input1,
                       std::int64_t rows_a,
                       std::int64_t cols_a,
                       std::int64_t cols_b,
                       const NPUConfig& config,
                       const std::string& bench_path,
                       const std::string& delay_profile_path,
                       bool estimate_only,
                       const std::string& task_name) {
    if (rows_a <= 0 || cols_a <= 0 || cols_b <= 0) {
        throw std::runtime_error("direct MatMul dimensions must be positive");
    }
    const std::size_t lhs_elems = static_cast<std::size_t>(rows_a * cols_a);
    const std::size_t rhs_elems = static_cast<std::size_t>(cols_a * cols_b);
    if (input0.size() != lhs_elems) {
        throw std::runtime_error("direct MatMul input0 size does not match rows_a * cols_a");
    }
    if (input1.size() != rhs_elems) {
        throw std::runtime_error("direct MatMul input1 size does not match cols_a * cols_b");
    }

    const RuntimeTopology topology = buildRuntimeTopology(config);
    std::ofstream bench(bench_path, std::ios::out | std::ios::trunc);
    if (!bench.is_open()) {
        throw std::runtime_error("cannot open NPU intra bench for write: " + bench_path);
    }

    Tensor a = tensorFromI64(input0, {rows_a, cols_a});
    Tensor b = tensorFromI64(input1, {cols_a, cols_b});
    std::uint64_t ops = 0;
    Tensor out = matmul2D(a, b, topology, ops);

    RunResult result;
    const IntraDelayProfile delay_profile = loadRunDelayProfile(config, delay_profile_path);
    ExternalMemoryAccounting external_memory(config);
    const OpActivity activity = buildMatMulActivity(rows_a, cols_a, cols_b, config, topology);
    std::uint64_t cycle = 0;
    accountExecutedOp(bench,
                      result,
                      cycle,
                      config,
                      topology,
                      delay_profile,
                      external_memory,
                      1,
                      task_name,
                      "MatMul",
                      out,
                      ops,
                      &activity);
    result.tile_events = planMatMulTiles(rows_a, cols_a, cols_b, config);
    bench.close();
    result.total_cycles = cycle;
    result.end_to_end_cycles = result.total_cycles;

    if (!estimate_only) {
        std::vector<std::int64_t> exact(static_cast<std::size_t>(rows_a * cols_b), 0);
        for (std::int64_t row = 0; row < rows_a; ++row) {
            for (std::int64_t col = 0; col < cols_b; ++col) {
                std::int64_t sum = 0;
                for (std::int64_t k = 0; k < cols_a; ++k) {
                    sum += input0[static_cast<std::size_t>(row * cols_a + k)] *
                           input1[static_cast<std::size_t>(k * cols_b + col)];
                }
                exact[static_cast<std::size_t>(row * cols_b + col)] = sum;
            }
        }
        result.output_tensors.push_back(out);
        result.output_i64 = std::move(exact);
    }
    return result;
}

std::vector<NpuTileEvent> planMatMulTiles(std::int64_t rows_a,
                                          std::int64_t cols_a,
                                          std::int64_t cols_b,
                                          const NPUConfig& config) {
    if (rows_a <= 0 || cols_a <= 0 || cols_b <= 0) {
        throw std::runtime_error("direct MatMul dimensions must be positive");
    }

    const RuntimeTopology topology = buildRuntimeTopology(config);
    const std::uint64_t logical_bytes =
        static_cast<std::uint64_t>(rows_a) * static_cast<std::uint64_t>(cols_a) *
            std::max<std::uint64_t>(1, config.activation_bytes) +
        static_cast<std::uint64_t>(cols_a) * static_cast<std::uint64_t>(cols_b) *
            std::max<std::uint64_t>(1, config.weight_bytes) +
        static_cast<std::uint64_t>(rows_a) * static_cast<std::uint64_t>(cols_b) *
            std::max<std::uint64_t>(1, config.output_bytes);
    const std::vector<WorkShard> shards = buildLinearSchedule(rows_a, logical_bytes, topology);

    std::vector<std::vector<MatMulTileEvent>> per_mac_events;
    per_mac_events.reserve(shards.size());
    for (const WorkShard& shard : shards) {
        const MacProfile& mac = topology.macs[static_cast<std::size_t>(shard.mac_id)];
        const std::int64_t local_m = std::max<std::int64_t>(0, shard.end - shard.begin);
        std::int64_t tm = 1;
        std::int64_t tn = 1;
        std::int64_t tk = 1;
        chooseMatMulTile(config, mac, local_m, cols_a, cols_b, tm, tn, tk);
        std::vector<MatMulTileEvent> local_events;

        for (std::int64_t mi = 0; mi < local_m; mi += tm) {
            const std::int64_t mt = std::min<std::int64_t>(tm, local_m - mi);
            for (std::int64_t nj = 0; nj < cols_b; nj += tn) {
                const std::int64_t nt = std::min<std::int64_t>(tn, cols_b - nj);
                for (std::int64_t kk = 0; kk < cols_a; kk += tk) {
                    const std::int64_t kt = std::min<std::int64_t>(tk, cols_a - kk);
                    const bool first_k = kk == 0;
                    const bool last_k = kk + kt >= cols_a;
                    const std::uint64_t a_bytes =
                        static_cast<std::uint64_t>(mt) * static_cast<std::uint64_t>(kt) *
                        std::max<std::uint64_t>(1, config.activation_bytes);
                    const std::uint64_t b_bytes =
                        static_cast<std::uint64_t>(kt) * static_cast<std::uint64_t>(nt) *
                        std::max<std::uint64_t>(1, config.weight_bytes);
                    const std::uint64_t psum_bytes =
                        static_cast<std::uint64_t>(mt) * static_cast<std::uint64_t>(nt) *
                        std::max<std::uint64_t>(1, config.accumulator_bytes);
                    const std::uint64_t c_bytes =
                        static_cast<std::uint64_t>(mt) * static_cast<std::uint64_t>(nt) *
                        std::max<std::uint64_t>(1, config.output_bytes);
                    const std::uint64_t footprint = a_bytes + b_bytes + psum_bytes + c_bytes;
                    const std::uint64_t ops =
                        2ULL * static_cast<std::uint64_t>(mt) * static_cast<std::uint64_t>(nt) *
                        static_cast<std::uint64_t>(kt);

                    ShardActivity local;
                    local.ops = ops;
                    local.spm_read_bytes = a_bytes + b_bytes + (first_k ? 0 : psum_bytes);
                    local.spm_write_bytes = last_k ? c_bytes : psum_bytes;
                    local.spm_miss_bytes =
                        footprint > mac.sram_bytes ? footprint - mac.sram_bytes : 0;
                    local.ddr_read_bytes = a_bytes + b_bytes;
                    local.ddr_write_bytes = last_k ? c_bytes : 0;
                    const double utilization = estimateArrayUtilization(mt, nt, config);
                    const std::uint64_t effective_ops_per_cycle =
                        std::max<std::uint64_t>(
                            1,
                            static_cast<std::uint64_t>(
                                std::floor(static_cast<double>(
                                               std::max<std::uint64_t>(1, mac.ops_per_cycle)) *
                                           utilization)));

                    MatMulTileEvent event;
                    event.mac_id = mac.mac_id;
                    event.node_id = mac.node_id;
                    event.ops = ops;
                    event.ddr_read_bytes = local.ddr_read_bytes;
                    event.ddr_write_bytes = local.ddr_write_bytes;
                    event.compute_cycles = ceilDiv(ops, effective_ops_per_cycle);
                    event.local_memory_cycles = estimateShardMemoryCycles(local, config, 0);
                    local_events.push_back(event);
                }
            }
        }
        per_mac_events.push_back(std::move(local_events));
    }

    // Interleave ready DMA work from different MAC streams.  A single NPU DMA
    // still serialises requests, but this avoids issuing every tile of MAC 0
    // before MAC 1 can become data-ready and lets the adapter expose genuine
    // per-MAC overlap.
    std::vector<MatMulTileEvent> events;
    std::size_t max_tiles_per_mac = 0;
    for (const auto& local_events : per_mac_events) {
        max_tiles_per_mac = std::max(max_tiles_per_mac, local_events.size());
    }
    std::uint64_t tile_id = 1;
    for (std::size_t ordinal = 0; ordinal < max_tiles_per_mac; ++ordinal) {
        for (const auto& local_events : per_mac_events) {
            if (ordinal < local_events.size()) {
                MatMulTileEvent event = local_events[ordinal];
                event.op_desc = 1;
                event.tile_id = tile_id++;
                events.push_back(event);
            }
        }
    }
    return events;
}

std::vector<MatMulTileEvent> planMatMulI64Tiles(std::int64_t rows_a,
                                                std::int64_t cols_a,
                                                std::int64_t cols_b,
                                                const NPUConfig& config) {
    return planMatMulTiles(rows_a, cols_a, cols_b, config);
}

NpuTileScheduleResult scheduleNpuTileEvents(
    const std::vector<NpuTileEvent>& events,
    const NPUConfig& config,
    std::uint64_t initial_cycle,
    std::uint64_t injected_intra_cycles,
    const NpuMemoryTransferCallback& transfer_callback) {
    NpuTileScheduleResult result;
    result.finish_cycle = initial_cycle;
    result.max_mac_finish_cycle = initial_cycle;
    result.dma_finish_cycle = initial_cycle;
    result.external_finish_cycle = initial_cycle;
    result.overall_finish_cycle = initial_cycle;
    result.injected_intra_cycles = injected_intra_cycles;
    if (events.empty()) {
        return result;
    }

    std::vector<std::uint64_t> mac_ready(
        static_cast<std::size_t>(std::max(1, config.mac_unit_count)), initial_cycle);
    std::uint64_t remaining_ops = 0;
    for (const NpuTileEvent& event : events) {
        remaining_ops += event.ops;
    }
    std::uint64_t remaining_intra = injected_intra_cycles;

    const auto transfer = [&](const NpuMemoryRequest& request,
                              std::uint64_t issue_cycle) -> std::uint64_t {
        if (request.bytes == 0 || !transfer_callback) {
            return issue_cycle;
        }
        const std::uint64_t complete = transfer_callback(request, issue_cycle);
        if (complete < issue_cycle) {
            throw std::runtime_error("NPU memory transfer callback completed before issue");
        }
        result.external_finish_cycle = std::max(result.external_finish_cycle, complete);
        return complete;
    };

    for (const NpuTileEvent& event : events) {
        if (event.mac_id < 0 || static_cast<std::size_t>(event.mac_id) >= mac_ready.size()) {
            throw std::runtime_error("NPU tile scheduler received an invalid MAC id");
        }
        NpuTileScheduleEntry entry;
        entry.tile = event;
        entry.read_issue_cycle = result.dma_finish_cycle;
        const NpuMemoryRequest read_request{
            (event.op_desc << 32) | (event.tile_id << 1),
            event.op_desc,
            event.tile_id,
            event.mac_id,
            false,
            event.ddr_read_bytes};
        entry.data_ready_cycle = transfer(read_request, entry.read_issue_cycle);
        result.dma_finish_cycle = entry.data_ready_cycle;

        const std::uint64_t intra_cycles =
            remaining_ops == event.ops
                ? remaining_intra
                : (remaining_intra * event.ops) / std::max<std::uint64_t>(1, remaining_ops);
        remaining_intra -= intra_cycles;
        remaining_ops -= event.ops;
        const std::uint64_t tile_core =
            config.compute_memory_mode == "max"
                ? std::max(event.compute_cycles, event.local_memory_cycles)
                : event.compute_cycles + event.local_memory_cycles;
        entry.mac_start_cycle = std::max(
            mac_ready[static_cast<std::size_t>(event.mac_id)], entry.data_ready_cycle);
        entry.mac_finish_cycle =
            entry.mac_start_cycle + std::max<std::uint64_t>(1, tile_core + intra_cycles);
        mac_ready[static_cast<std::size_t>(event.mac_id)] = entry.mac_finish_cycle;
        result.max_mac_finish_cycle = std::max(result.max_mac_finish_cycle, entry.mac_finish_cycle);

        entry.write_issue_cycle = std::max(result.dma_finish_cycle, entry.mac_finish_cycle);
        const NpuMemoryRequest write_request{
            (event.op_desc << 32) | (event.tile_id << 1) | 1ULL,
            event.op_desc,
            event.tile_id,
            event.mac_id,
            true,
            event.ddr_write_bytes};
        entry.write_complete_cycle = transfer(write_request, entry.write_issue_cycle);
        if (event.ddr_write_bytes > 0) {
            result.dma_finish_cycle = entry.write_complete_cycle;
        }
        result.entries.push_back(entry);
    }
    if (remaining_intra != 0 || remaining_ops != 0) {
        throw std::runtime_error("NPU tile scheduler did not consume all work or intra delay");
    }
    result.max_mac_finish_cycle += config.pipeline_depth_cycles;
    result.finish_cycle = std::max(result.max_mac_finish_cycle, result.dma_finish_cycle);
    result.overall_finish_cycle = std::max(result.finish_cycle, result.external_finish_cycle);
    return result;
}

void writeNpuProgramIntraBench(const std::vector<NpuProgramEvent>& events,
                               const NPUConfig& config,
                               const std::string& bench_path) {
    if (bench_path.empty()) {
        throw std::runtime_error("NPU intra bench path is empty");
    }
    const RuntimeTopology topology = buildRuntimeTopology(config);
    const NpuProgramScheduleResult baseline =
        scheduleNpuProgramEvents(events, config, 0, NpuMemoryTransferCallback{});

    struct TaskTraffic {
        std::uint64_t start_cycle = std::numeric_limits<std::uint64_t>::max();
        std::uint64_t finish_cycle = 0;
        std::uint64_t dma_bytes = 0;
        bool has_compute = false;
        std::set<int> mac_ids;
    };
    std::map<std::uint64_t, TaskTraffic> tasks;
    for (const NpuProgramScheduleEntry& entry : baseline.entries) {
        const NpuProgramEvent& event = entry.event;
        if (event.op_desc == 0 || event.kind == NpuProgramEventKind::kBarrier) {
            continue;
        }
        TaskTraffic& task = tasks[event.op_desc];
        task.start_cycle = std::min(task.start_cycle, entry.issue_cycle);
        task.finish_cycle = std::max(task.finish_cycle, entry.complete_cycle);
        if (event.kind == NpuProgramEventKind::kDmaLoad ||
            event.kind == NpuProgramEventKind::kDmaStore) {
            task.dma_bytes += event.bytes;
        }
        if (event.kind == NpuProgramEventKind::kMacCompute) {
            task.has_compute = true;
        }
        if (event.kind == NpuProgramEventKind::kMacCompute && event.mac_id >= 0) {
            task.mac_ids.insert(event.mac_id);
        }
    }

    std::ofstream bench(bench_path, std::ios::out | std::ios::trunc);
    if (!bench.is_open()) {
        throw std::runtime_error("cannot open NPU intra bench for write: " + bench_path);
    }
    std::uint64_t packet_count = 0;
    for (const auto& item : tasks) {
        const std::uint64_t desc = item.first;
        const TaskTraffic& task = item.second;
        if (!task.has_compute) {
            continue;
        }
        std::set<int> active_mac_ids = task.mac_ids;
        // A vector/reduction-only descriptor has no MAC-array traffic in the
        // current topology model.  Do not manufacture controller broadcasts
        // for it: that would make its profile unrelated to real hardware
        // packets.  Such operators remain governed by the vector/reduce
        // scheduler and their DRAM dependencies.
        if (active_mac_ids.empty()) {
            continue;
        }
        std::vector<WorkShard> shards;
        std::vector<std::uint64_t> shard_bytes;
        std::vector<std::uint64_t> shard_cycles;
        const std::uint64_t per_mac_bytes = ceilDiv(
            std::max<std::uint64_t>(1, task.dma_bytes),
            static_cast<std::uint64_t>(std::max<std::size_t>(1, active_mac_ids.size())));
        const std::uint64_t task_cycles = std::max<std::uint64_t>(
            1, task.finish_cycle >= task.start_cycle ? task.finish_cycle - task.start_cycle : 1);
        for (int mac_id : active_mac_ids) {
            if (mac_id < 0 || static_cast<std::size_t>(mac_id) >= topology.macs.size()) {
                throw std::runtime_error("NPU intra bench received an invalid MAC id");
            }
            const MacProfile& mac = topology.macs[static_cast<std::size_t>(mac_id)];
            shards.push_back({mac.mac_id, mac.node_id, 0, 1});
            shard_bytes.push_back(per_mac_bytes);
            shard_cycles.push_back(task_cycles);
        }
        emitBenchForNode(bench,
                         task.start_cycle == std::numeric_limits<std::uint64_t>::max()
                             ? 0
                             : task.start_cycle,
                         desc,
                         config,
                         topology,
                         shards,
                         shard_bytes,
                         shard_cycles,
                         packet_count);
    }
}

NpuProgramScheduleResult scheduleNpuProgramEvents(
    const std::vector<NpuProgramEvent>& events,
    const NPUConfig& config,
    std::uint64_t initial_cycle,
    const NpuMemoryTransferCallback& transfer_callback,
    const IntraDelayProfile* intra_delay_profile,
    const NpuRequestCompletionResolver& request_completion_resolver) {
    NpuProgramScheduleResult result;
    result.finish_cycle = initial_cycle;
    result.dma_finish_cycle = initial_cycle;
    result.mac_finish_cycle = initial_cycle;
    result.vector_finish_cycle = initial_cycle;
    result.reduce_finish_cycle = initial_cycle;
    result.external_finish_cycle = initial_cycle;
    result.overall_finish_cycle = initial_cycle;

    std::vector<std::uint64_t> mac_ready(
        static_cast<std::size_t>(std::max(1, config.mac_unit_count)), initial_cycle);
    std::uint64_t dma_ready = initial_cycle;
    std::uint64_t vector_ready = initial_cycle;
    std::uint64_t reduce_ready = initial_cycle;
    std::set<NpuEventId> seen_ids;
    std::map<std::uint64_t, std::uint64_t> task_intra_ready;
    std::map<std::uint64_t, std::uint64_t> request_ready_cycles;

    const auto resolve_request = [&](std::uint64_t request_id) -> std::optional<std::uint64_t> {
        const auto memo = request_ready_cycles.find(request_id);
        if (memo != request_ready_cycles.end()) {
            return memo->second;
        }
        if (!request_completion_resolver) {
            return std::nullopt;
        }
        const std::optional<std::uint64_t> resolved = request_completion_resolver(request_id);
        if (resolved.has_value()) {
            request_ready_cycles.emplace(request_id, *resolved);
        }
        return resolved;
    };

    const auto transfer = [&](const NpuMemoryRequest& request,
                              std::uint64_t issue_cycle) -> std::uint64_t {
        if (request.bytes == 0) {
            return issue_cycle;
        }
        if (!transfer_callback) {
            // This is only the NPU-side DDR-port transfer time.  A workload
            // that needs DRAM-chiplet service must supply its normal
            // callback, which returns an absolute externally observed cycle.
            return issue_cycle + ceilDiv(request.bytes, config.ddr_bandwidth_bytes_per_cycle);
        }
        const std::uint64_t complete = transfer_callback(request, issue_cycle);
        if (complete < issue_cycle) {
            throw std::runtime_error("NPU program memory callback completed before issue");
        }
        result.external_finish_cycle = std::max(result.external_finish_cycle, complete);
        return complete;
    };

    for (const NpuProgramEvent& event : events) {
        if (event.id == 0 || !seen_ids.insert(event.id).second) {
            throw std::runtime_error("NPU program contains a missing or duplicate event id");
        }

        std::uint64_t dependency_ready = initial_cycle;
        for (const NpuEventId dependency : event.dependencies) {
            const auto it = result.event_complete_cycles.find(dependency);
            if (it == result.event_complete_cycles.end()) {
                throw std::runtime_error(
                    "NPU program dependency must reference an earlier recorded event");
            }
            dependency_ready = std::max(dependency_ready, it->second);
        }

        for (const std::uint64_t request_id : event.wait_request_ids) {
            const std::optional<std::uint64_t> ready = resolve_request(request_id);
            if (!ready.has_value()) {
                throw std::runtime_error(
                    "NPU program waits on DRAM request_id " + std::to_string(request_id) +
                    " but no completion is available");
            }
            dependency_ready = std::max(dependency_ready, *ready);
        }

        // The current intra topology explicitly models controller-to-MAC
        // traffic.  Apply its PopNet delay only at MAC-array work, not to a
        // vector/reduction-only descriptor for which no intra packets were
        // emitted.  This keeps profile TASK records and runtime injection
        // one-to-one.
        const bool is_intra_modeled_compute =
            event.kind == NpuProgramEventKind::kMacCompute;
        if (is_intra_modeled_compute && intra_delay_profile != nullptr && event.op_desc != 0) {
            auto gate = task_intra_ready.find(event.op_desc);
            if (gate == task_intra_ready.end()) {
                const auto delay = intra_delay_profile->task_dst_delay.find(event.op_desc);
                if (delay == intra_delay_profile->task_dst_delay.end()) {
                    throw std::runtime_error(
                        "NPU intra delay profile is missing TASK " +
                        std::to_string(event.op_desc) +
                        "; regenerate the profile from this exact event program");
                }
                const std::uint64_t injected = static_cast<std::uint64_t>(std::llround(
                    static_cast<double>(delay->second) *
                    std::max(0.0, config.intra_delay_scale)));
                gate = task_intra_ready.emplace(event.op_desc, dependency_ready + injected).first;
                result.injected_intra_cycles += injected;
            }
            dependency_ready = std::max(dependency_ready, gate->second);
        }

        NpuProgramScheduleEntry entry;
        entry.event = event;
        entry.ready_cycle = dependency_ready;
        switch (event.kind) {
            case NpuProgramEventKind::kDmaLoad:
            case NpuProgramEventKind::kDmaStore: {
                entry.issue_cycle = std::max(dma_ready, dependency_ready);
                entry.start_cycle = entry.issue_cycle;
                const NpuMemoryRequest request{
                    event.id,
                    event.op_desc,
                    event.id,
                    -1,
                    event.kind == NpuProgramEventKind::kDmaStore,
                    event.bytes,
                    event.address};
                entry.complete_cycle = transfer(request, entry.issue_cycle);
                dma_ready = entry.complete_cycle;
                result.dma_finish_cycle = std::max(result.dma_finish_cycle, entry.complete_cycle);
                break;
            }
            case NpuProgramEventKind::kMacCompute: {
                if (event.mac_id < 0 ||
                    static_cast<std::size_t>(event.mac_id) >= mac_ready.size()) {
                    throw std::runtime_error("NPU program MAC event has an invalid MAC id");
                }
                entry.issue_cycle = dependency_ready;
                entry.start_cycle = std::max(
                    mac_ready[static_cast<std::size_t>(event.mac_id)], dependency_ready);
                entry.complete_cycle = entry.start_cycle +
                    ceilDiv(event.ops, config.mac_ops_per_cycle);
                mac_ready[static_cast<std::size_t>(event.mac_id)] = entry.complete_cycle;
                result.mac_finish_cycle = std::max(result.mac_finish_cycle, entry.complete_cycle);
                break;
            }
            case NpuProgramEventKind::kVectorCompute: {
                entry.issue_cycle = dependency_ready;
                entry.start_cycle = std::max(vector_ready, dependency_ready);
                entry.complete_cycle = entry.start_cycle +
                    ceilDiv(event.ops, config.vector_ops_per_cycle);
                vector_ready = entry.complete_cycle;
                result.vector_finish_cycle = std::max(result.vector_finish_cycle, entry.complete_cycle);
                break;
            }
            case NpuProgramEventKind::kReduceCompute: {
                entry.issue_cycle = dependency_ready;
                entry.start_cycle = std::max(reduce_ready, dependency_ready);
                entry.complete_cycle = entry.start_cycle +
                    ceilDiv(event.ops, config.reduce_ops_per_cycle);
                reduce_ready = entry.complete_cycle;
                result.reduce_finish_cycle = std::max(result.reduce_finish_cycle, entry.complete_cycle);
                break;
            }
            case NpuProgramEventKind::kBarrier:
                entry.issue_cycle = dependency_ready;
                entry.start_cycle = dependency_ready;
                entry.complete_cycle = dependency_ready;
                break;
            default:
                throw std::runtime_error("NPU program contains an unknown event kind");
        }
        result.event_complete_cycles.emplace(event.id, entry.complete_cycle);
        result.entries.push_back(entry);
        result.finish_cycle = std::max(result.finish_cycle, entry.complete_cycle);
    }
    result.overall_finish_cycle = std::max(result.finish_cycle, result.external_finish_cycle);
    return result;
}

void writeJsonReport(const std::string& path, const RunResult& result) {
    if (path.empty()) {
        return;
    }
    std::ofstream out(path, std::ios::out | std::ios::trunc);
    if (!out.is_open()) {
        return;
    }
    nlohmann::json root;
    root["compute_cycles"] = result.compute_cycles;
    root["injected_intra_cycles"] = result.injected_intra_cycles;
    root["total_cycles"] = result.total_cycles;
    root["emitted_packets"] = result.emitted_packets;
    root["ddr_read_bytes"] = result.ddr_read_bytes;
    root["ddr_write_bytes"] = result.ddr_write_bytes;
    root["ddr_bytes"] = result.ddr_read_bytes + result.ddr_write_bytes;
    root["dram_read_transactions"] = result.dram_read_transactions;
    root["dram_write_transactions"] = result.dram_write_transactions;
    root["dram_transactions"] = result.dram_read_transactions + result.dram_write_transactions;
    root["dram_cycles"] = result.dram_cycles;
    root["tile_scheduled_cycles"] = result.tile_scheduled_cycles;
    root["end_to_end_cycles"] =
        result.end_to_end_cycles == 0 ? result.total_cycles : result.end_to_end_cycles;
    root["output_elements"] = result.output_i64.size();
    root["nodes"] = nlohmann::json::array();
    for (const auto& n : result.node_reports) {
        nlohmann::json node_json = {
            {"name", n.name},
            {"op_type", n.op_type},
            {"ops", n.ops},
            {"bytes", n.bytes},
            {"compute_cycles", n.compute_cycles},
            {"memory_cycles", n.memory_cycles},
            {"injected_intra_cycles", n.injected_intra_cycles},
            {"total_cycles", n.total_cycles},
            {"spm_read_accesses", n.spm_read_accesses},
            {"spm_write_accesses", n.spm_write_accesses},
            {"spm_accesses", n.spm_read_accesses + n.spm_write_accesses},
            {"spm_miss_accesses", n.spm_miss_accesses},
            {"spm_read_bytes", n.spm_read_bytes},
            {"spm_write_bytes", n.spm_write_bytes},
            {"spm_bytes", n.spm_read_bytes + n.spm_write_bytes},
            {"input_read_bytes", n.input_read_bytes},
            {"weight_read_bytes", n.weight_read_bytes},
            {"psum_read_bytes", n.psum_read_bytes},
            {"psum_write_bytes", n.psum_write_bytes},
            {"output_write_bytes", n.output_write_bytes},
            {"ddr_read_bytes", n.ddr_read_bytes},
            {"ddr_write_bytes", n.ddr_write_bytes},
            {"ddr_bytes", n.ddr_read_bytes + n.ddr_write_bytes},
            {"dram_read_transactions", n.dram_read_transactions},
            {"dram_write_transactions", n.dram_write_transactions},
            {"dram_transactions", n.dram_read_transactions + n.dram_write_transactions},
            {"dram_cycles", n.dram_cycles},
            {"tile_count", n.tile_count},
            {"array_utilization", n.array_utilization},
            {"active_macs", n.active_macs},
        };
        node_json["mac_units"] = nlohmann::json::array();
        for (const auto& unit : n.mac_units) {
            node_json["mac_units"].push_back({
                {"mac_id", unit.mac_id},
                {"node_id", unit.node_id},
                {"ops", unit.ops},
                {"bytes", unit.bytes},
                {"compute_cycles", unit.compute_cycles},
                {"memory_cycles", unit.memory_cycles},
                {"total_cycles", unit.total_cycles},
                {"spm_read_accesses", unit.spm_read_accesses},
                {"spm_write_accesses", unit.spm_write_accesses},
                {"spm_accesses", unit.spm_read_accesses + unit.spm_write_accesses},
                {"spm_miss_accesses", unit.spm_miss_accesses},
                {"spm_read_bytes", unit.spm_read_bytes},
                {"spm_write_bytes", unit.spm_write_bytes},
                {"spm_bytes", unit.spm_read_bytes + unit.spm_write_bytes},
                {"input_read_bytes", unit.input_read_bytes},
                {"weight_read_bytes", unit.weight_read_bytes},
                {"psum_read_bytes", unit.psum_read_bytes},
                {"psum_write_bytes", unit.psum_write_bytes},
                {"output_write_bytes", unit.output_write_bytes},
                {"ddr_read_bytes", unit.ddr_read_bytes},
                {"ddr_write_bytes", unit.ddr_write_bytes},
                {"ddr_bytes", unit.ddr_read_bytes + unit.ddr_write_bytes},
                {"dram_read_transactions", unit.dram_read_transactions},
                {"dram_write_transactions", unit.dram_write_transactions},
                {"dram_transactions", unit.dram_read_transactions + unit.dram_write_transactions},
                {"dram_cycles", unit.dram_cycles},
                {"tile_count", unit.tile_count},
                {"array_utilization", unit.array_utilization},
            });
        }
        root["nodes"].push_back(std::move(node_json));
    }
    out << root.dump(2) << "\n";
}

}  // namespace NPUSim

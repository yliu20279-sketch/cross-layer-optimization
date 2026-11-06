#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "../interchiplet/includes/pipe_comm.h"
#include "../interchiplet/includes/sync_protocol.h"
#include "onnx_event_lowering.h"
#include "npusim_chiplet_runtime.h"
#include "npusim_runtime.h"

namespace {

InterChiplet::PipeComm g_pipe_comm;

std::vector<char> readBinaryFile(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in.is_open()) {
        throw std::runtime_error("cannot open file: " + path);
    }
    return std::vector<char>((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
}

std::vector<std::int64_t> readIntTextFile(const std::string& path) {
    if (path.empty() || path == "-") {
        return {};
    }
    std::ifstream in(path);
    if (!in.is_open()) {
        throw std::runtime_error("cannot open input text file: " + path);
    }
    std::vector<std::int64_t> values;
    std::int64_t value = 0;
    while (in >> value) {
        values.push_back(value);
    }
    return values;
}

std::string getEnvString(const char* key, const std::string& fallback) {
    const char* value = std::getenv(key);
    return value == nullptr || value[0] == '\0' ? fallback : std::string(value);
}

bool getEnvBool(const char* key, bool fallback, bool* present = nullptr) {
    const char* value = std::getenv(key);
    if (value == nullptr || value[0] == '\0') {
        if (present != nullptr) {
            *present = false;
        }
        return fallback;
    }
    if (present != nullptr) {
        *present = true;
    }
    const std::string text(value);
    return text != "0" && text != "false" && text != "FALSE" && text != "no" && text != "NO";
}

void applyTopologyOverride(NPUSim::NPUConfig& cfg, const std::string& gv_path, int node_count) {
    if (gv_path.empty()) {
        throw std::runtime_error(
            "NPUSim requires an explicit topology gv argument. Pass --topology-gv from the benchmark yml "
            "or set NPUSIM_TOPOLOGY_GV for local debugging.");
    }
    if (!gv_path.empty()) {
        cfg.topology_mode = "custom_gv";
        cfg.topology_gv_path = gv_path;
    }
    if (node_count > 0) {
        cfg.topology_node_count = node_count;
    }
}

int parseIntArg(const char* text, int fallback) {
    if (text == nullptr) {
        return fallback;
    }
    char* end = nullptr;
    const long value = std::strtol(text, &end, 0);
    return end != text && *end == '\0' ? static_cast<int>(value) : fallback;
}

std::int64_t parseI64Arg(const char* text, const std::string& name) {
    if (text == nullptr) {
        throw std::invalid_argument("missing value for " + name);
    }
    char* end = nullptr;
    const long long value = std::strtoll(text, &end, 0);
    if (end == text || *end != '\0') {
        throw std::invalid_argument("invalid integer for " + name + ": " + text);
    }
    return static_cast<std::int64_t>(value);
}

void parseCommonOverrides(int begin,
                          int argc,
                          char** argv,
                          std::string& topology_gv,
                          int& node_count,
                          bool& intra_delay_override_set,
                          bool& intra_delay_enable,
                          std::string* report_directory = nullptr) {
    for (int i = begin; i < argc; ++i) {
        const std::string opt = argv[i];
        auto needValue = [&](const std::string& name) -> const char* {
            if (i + 1 >= argc) {
                throw std::invalid_argument("missing value for " + name);
            }
            return argv[++i];
        };
        if (opt == "--topology-gv" || opt == "--npu-topology-gv") {
            topology_gv = needValue(opt);
        } else if (opt == "--node-count" || opt == "--npu-node-count") {
            node_count = parseIntArg(needValue(opt), node_count);
        } else if (opt == "--no-intra-delay" || opt == "--npu-no-intra-delay") {
            intra_delay_override_set = true;
            intra_delay_enable = false;
        } else if (opt == "--intra-delay" || opt == "--npu-intra-delay") {
            intra_delay_override_set = true;
            intra_delay_enable = true;
        } else if (opt == "--report-dir") {
            if (report_directory == nullptr) {
                throw std::invalid_argument("--report-dir is only valid for --chiplet-onnx");
            }
            *report_directory = needValue(opt);
        } else {
            throw std::invalid_argument("unknown NPUSim option: " + opt);
        }
    }
}

template <typename T>
void receivePayload(int src_x,
                    int src_y,
                    int dst_x,
                    int dst_y,
                    T* payload,
                    std::size_t count,
                    unsigned long long& chip_cycle) {
    if (payload == nullptr || count == 0) {
        return;
    }
    const int bytes = static_cast<int>(count * sizeof(T));
    const std::string pipe = InterChiplet::receiveSync(src_x, src_y, dst_x, dst_y);
    g_pipe_comm.read_data(pipe.c_str(), payload, bytes);
    chip_cycle = InterChiplet::readSync(chip_cycle, src_x, src_y, dst_x, dst_y, bytes, 0);
}

template <typename T>
void sendPayload(int src_x,
                 int src_y,
                 int dst_x,
                 int dst_y,
                 T* payload,
                 std::size_t count,
                 unsigned long long& chip_cycle) {
    if (payload == nullptr || count == 0) {
        return;
    }
    const int bytes = static_cast<int>(count * sizeof(T));
    const std::string pipe = InterChiplet::sendSync(src_x, src_y, dst_x, dst_y);
    g_pipe_comm.write_data(pipe.c_str(), payload, bytes);
    chip_cycle = InterChiplet::writeSync(chip_cycle, src_x, src_y, dst_x, dst_y, bytes, 0);
}

int runLocal(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "usage: npusim --local <model.onnx> [input0.txt] [input1.txt] --topology-gv <topology.gv>\n";
        return 1;
    }
    const std::string model_path = argv[2];
    std::string input0_path;
    std::string input1_path;
    int opt_begin = 3;
    if (opt_begin < argc && std::string(argv[opt_begin]).rfind("--", 0) != 0) {
        input0_path = argv[opt_begin++];
    }
    if (opt_begin < argc && std::string(argv[opt_begin]).rfind("--", 0) != 0) {
        input1_path = argv[opt_begin++];
    }
    const std::string cfg_path = getEnvString("NPUSIM_CONFIG", "npu_config.json");
    std::string topology_gv = getEnvString("NPUSIM_TOPOLOGY_GV", "");
    int node_count = parseIntArg(std::getenv("NPUSIM_NODE_COUNT"), 0);
    bool intra_delay_override_set = false;
    bool intra_delay_enable =
        getEnvBool("NPUSIM_INTRA_DELAY_ENABLE", true, &intra_delay_override_set);
    parseCommonOverrides(opt_begin,
                         argc,
                         argv,
                         topology_gv,
                         node_count,
                         intra_delay_override_set,
                         intra_delay_enable);
    const std::string bench_path = getEnvString("NPUSIM_BENCH", "bench.txt");
    const std::string delay_path = getEnvString("NPUSIM_DELAY_PROFILE", "reports/npu_intra_delay_profile.txt");
    const std::string report_path = getEnvString("NPUSIM_REPORT", "reports/npu_report.json");

    NPUSim::NPUConfig cfg = NPUSim::loadConfig(cfg_path);
    applyTopologyOverride(cfg, topology_gv, node_count);
    if (intra_delay_override_set) {
        cfg.intra_delay_enable = intra_delay_enable;
    }
    const std::vector<char> model = readBinaryFile(model_path);
    const std::vector<std::int64_t> input0 = readIntTextFile(input0_path);
    const std::vector<std::int64_t> input1 = readIntTextFile(input1_path);

    const NPUSim::RunResult result =
        NPUSim::runModel(model, input0, input1, cfg, bench_path, delay_path, false);
    NPUSim::writeJsonReport(report_path, result);

    std::cout << "[NPUSim ][LOCAL] model=" << model_path
              << " output_elements=" << result.output_i64.size()
              << " total_cycles=" << result.total_cycles
              << " injected_intra_cycles=" << result.injected_intra_cycles
              << " ddr_bytes=" << (result.ddr_read_bytes + result.ddr_write_bytes)
              << " dram_cycles=" << result.dram_cycles
              << " bench=" << bench_path
              << " report=" << report_path << std::endl;
    return 0;
}

int runDirectMatMul(int argc, char** argv) {
    if (argc < 7) {
        std::cerr << "usage: npusim --matmul <rows_a> <cols_a> <cols_b> "
                     "<input0.txt> <input1.txt> --topology-gv <topology.gv>\n";
        return 1;
    }
    const std::int64_t rows_a = parseI64Arg(argv[2], "rows_a");
    const std::int64_t cols_a = parseI64Arg(argv[3], "cols_a");
    const std::int64_t cols_b = parseI64Arg(argv[4], "cols_b");
    const std::string input0_path = argv[5];
    const std::string input1_path = argv[6];

    const std::string cfg_path = getEnvString("NPUSIM_CONFIG", "npu_config.json");
    std::string topology_gv = getEnvString("NPUSIM_TOPOLOGY_GV", "");
    int node_count = parseIntArg(std::getenv("NPUSIM_NODE_COUNT"), 0);
    bool intra_delay_override_set = false;
    bool intra_delay_enable =
        getEnvBool("NPUSIM_INTRA_DELAY_ENABLE", false, &intra_delay_override_set);
    parseCommonOverrides(7,
                         argc,
                         argv,
                         topology_gv,
                         node_count,
                         intra_delay_override_set,
                         intra_delay_enable);
    const std::string bench_path = getEnvString("NPUSIM_BENCH", "bench.txt");
    const std::string delay_path = getEnvString("NPUSIM_DELAY_PROFILE", "reports/npu_intra_delay_profile.txt");
    const std::string report_path = getEnvString("NPUSIM_REPORT", "reports/npu_report.json");

    NPUSim::NPUConfig cfg = NPUSim::loadConfig(cfg_path);
    applyTopologyOverride(cfg, topology_gv, node_count);
    cfg.intra_delay_enable = intra_delay_override_set ? intra_delay_enable : false;

    const std::vector<std::int64_t> input0 = readIntTextFile(input0_path);
    const std::vector<std::int64_t> input1 = readIntTextFile(input1_path);
    const NPUSim::RunResult result =
        NPUSim::runMatMulI64(input0,
                             input1,
                             rows_a,
                             cols_a,
                             cols_b,
                             cfg,
                             bench_path,
                             delay_path,
                             false,
                             "direct_matmul");
    NPUSim::writeJsonReport(report_path, result);

    std::cout << "[NPUSim ][MATMUL] shape=" << rows_a << "x" << cols_a
              << " * " << cols_a << "x" << cols_b
              << " output_elements=" << result.output_i64.size()
              << " total_cycles=" << result.total_cycles
              << " injected_intra_cycles=" << result.injected_intra_cycles
              << " ddr_bytes=" << (result.ddr_read_bytes + result.ddr_write_bytes)
              << " dram_cycles=" << result.dram_cycles
              << " bench=" << bench_path
              << " report=" << report_path << std::endl;
    return 0;
}

int runOnnxEventLowering(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "usage: npusim --lower-events <model.onnx> --topology-gv <topology.gv>\n";
        return 1;
    }
    const std::string model_path = argv[2];
    const std::string cfg_path = getEnvString("NPUSIM_CONFIG", "npu_config.json");
    std::string topology_gv = getEnvString("NPUSIM_TOPOLOGY_GV", "");
    int node_count = parseIntArg(std::getenv("NPUSIM_NODE_COUNT"), 0);
    bool intra_delay_override_set = false;
    bool intra_delay_enable =
        getEnvBool("NPUSIM_INTRA_DELAY_ENABLE", false, &intra_delay_override_set);
    parseCommonOverrides(3,
                         argc,
                         argv,
                         topology_gv,
                         node_count,
                         intra_delay_override_set,
                         intra_delay_enable);

    NPUSim::NPUConfig cfg = NPUSim::loadConfig(cfg_path);
    applyTopologyOverride(cfg, topology_gv, node_count);
    const std::vector<char> model = readBinaryFile(model_path);
    const NPUSim::OnnxEventLoweringResult lowered =
        NPUSim::lowerOnnxBytesToProgramEvents(model, cfg);
    const NPUSim::NpuProgramScheduleResult schedule =
        NPUSim::scheduleNpuProgramEvents(lowered.events, cfg, 0);
    std::size_t dma_loads = 0;
    std::size_t dma_stores = 0;
    std::size_t mac_events = 0;
    std::size_t vector_events = 0;
    std::size_t reduce_events = 0;
    std::size_t barriers = 0;
    for (const NPUSim::NpuProgramEvent& event : lowered.events) {
        switch (event.kind) {
            case NPUSim::NpuProgramEventKind::kDmaLoad:
                ++dma_loads;
                break;
            case NPUSim::NpuProgramEventKind::kDmaStore:
                ++dma_stores;
                break;
            case NPUSim::NpuProgramEventKind::kMacCompute:
                ++mac_events;
                break;
            case NPUSim::NpuProgramEventKind::kVectorCompute:
                ++vector_events;
                break;
            case NPUSim::NpuProgramEventKind::kReduceCompute:
                ++reduce_events;
                break;
            case NPUSim::NpuProgramEventKind::kBarrier:
                ++barriers;
                break;
        }
    }
    std::cout << "[NPUSim ][ONNX-LOWER] model=" << model_path
              << " events=" << lowered.events.size()
              << " tensors=" << lowered.tensor_addresses.size()
              << " cycles=" << schedule.finish_cycle
              << " dma_load=" << dma_loads
              << " dma_store=" << dma_stores
              << " mac=" << mac_events
              << " vector=" << vector_events
              << " reduce=" << reduce_events
              << " barrier=" << barriers
              << " memory_model=ddr_bandwidth_fallback" << std::endl;
    return 0;
}

int runOnnxIntraBench(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "usage: npusim --intra-bench <model.onnx> --topology-gv <topology.gv>\n";
        return 1;
    }
    const std::string model_path = argv[2];
    const std::string cfg_path = getEnvString("NPUSIM_CONFIG", "npu_config.json");
    std::string topology_gv = getEnvString("NPUSIM_TOPOLOGY_GV", "");
    int node_count = parseIntArg(std::getenv("NPUSIM_NODE_COUNT"), 0);
    bool intra_delay_override_set = false;
    bool intra_delay_enable = false;
    parseCommonOverrides(3,
                         argc,
                         argv,
                         topology_gv,
                         node_count,
                         intra_delay_override_set,
                         intra_delay_enable);
    const std::string bench_path = getEnvString("NPUSIM_BENCH", "bench_npu_intra.txt");

    NPUSim::NPUConfig cfg = NPUSim::loadConfig(cfg_path);
    applyTopologyOverride(cfg, topology_gv, node_count);
    const NPUSim::OnnxEventLoweringResult lowered =
        NPUSim::lowerOnnxBytesToProgramEvents(readBinaryFile(model_path), cfg);
    NPUSim::writeNpuProgramIntraBench(lowered.events, cfg, bench_path);
    std::cout << "[NPUSim ][ONNX-INTRA-BENCH] model=" << model_path
              << " events=" << lowered.events.size()
              << " bench=" << bench_path << std::endl;
    return 0;
}

struct EventCounts {
    std::size_t dma_loads = 0;
    std::size_t dma_stores = 0;
    std::size_t mac_events = 0;
    std::size_t vector_events = 0;
    std::size_t reduce_events = 0;
    std::size_t barriers = 0;
};

EventCounts countProgramEvents(const std::vector<NPUSim::NpuProgramEvent>& events) {
    EventCounts counts;
    for (const NPUSim::NpuProgramEvent& event : events) {
        switch (event.kind) {
            case NPUSim::NpuProgramEventKind::kDmaLoad:
                ++counts.dma_loads;
                break;
            case NPUSim::NpuProgramEventKind::kDmaStore:
                ++counts.dma_stores;
                break;
            case NPUSim::NpuProgramEventKind::kMacCompute:
                ++counts.mac_events;
                break;
            case NPUSim::NpuProgramEventKind::kVectorCompute:
                ++counts.vector_events;
                break;
            case NPUSim::NpuProgramEventKind::kReduceCompute:
                ++counts.reduce_events;
                break;
            case NPUSim::NpuProgramEventKind::kBarrier:
                ++counts.barriers;
                break;
        }
    }
    return counts;
}

void writeOnnxChipletScheduleReport(const std::string& path,
                                    const NPUSim::OnnxEventLoweringResult& lowered,
                                    const NPUSim::NpuProgramScheduleResult& schedule,
                                    const std::vector<NPUSim::ChipletDramCompletionRecord>& completions,
                                    const EventCounts& counts,
                                    int self_x,
                                    int self_y,
                                    std::uint64_t chip_cycle) {
    const std::filesystem::path report_path(path);
    if (!report_path.parent_path().empty()) {
        std::filesystem::create_directories(report_path.parent_path());
    }
    std::ofstream output(path, std::ios::out | std::ios::trunc);
    if (!output.is_open()) {
        throw std::runtime_error("cannot open ONNX chiplet schedule report: " + path);
    }
    output << "{\n"
           << "  \"mode\": \"onnx_chiplet_timing\",\n"
           << "  \"coordinate\": [" << self_x << ", " << self_y << "],\n"
           << "  \"functional_execution\": false,\n"
           << "  \"event_count\": " << lowered.events.size() << ",\n"
           << "  \"tensor_count\": " << lowered.tensor_addresses.size() << ",\n"
           << "  \"dma_load_events\": " << counts.dma_loads << ",\n"
           << "  \"dma_store_events\": " << counts.dma_stores << ",\n"
           << "  \"mac_events\": " << counts.mac_events << ",\n"
           << "  \"vector_events\": " << counts.vector_events << ",\n"
           << "  \"reduce_events\": " << counts.reduce_events << ",\n"
           << "  \"barrier_events\": " << counts.barriers << ",\n"
           << "  \"finish_cycle\": " << schedule.finish_cycle << ",\n"
           << "  \"npu_schedule_finish_cycle\": " << schedule.finish_cycle << ",\n"
           << "  \"dma_finish_cycle\": " << schedule.dma_finish_cycle << ",\n"
           << "  \"external_finish_cycle\": " << schedule.external_finish_cycle << ",\n"
           << "  \"overall_finish_cycle\": " << schedule.overall_finish_cycle << ",\n"
           << "  \"mac_finish_cycle\": " << schedule.mac_finish_cycle << ",\n"
           << "  \"vector_finish_cycle\": " << schedule.vector_finish_cycle << ",\n"
           << "  \"reduce_finish_cycle\": " << schedule.reduce_finish_cycle << ",\n"
           << "  \"injected_intra_cycles\": " << schedule.injected_intra_cycles << ",\n"
           << "  \"dram_completion_count\": " << completions.size() << ",\n"
           << "  \"dram_completion_gated\": true,\n"
           << "  \"external_memory_end_cycle\": " << chip_cycle << ",\n"
           << "  \"chiplet_end_cycle\": " << chip_cycle << "\n"
           << "}\n";
}

int runOnnxChiplet(int argc, char** argv) {
    if (argc < 5) {
        std::cerr << "usage: npusim --chiplet-onnx <self_x> <self_y> <model.onnx> "
                     "--topology-gv <topology.gv> [--report-dir <dir>]\n";
        return 1;
    }
    const int self_x = parseIntArg(argv[2], -1);
    const int self_y = parseIntArg(argv[3], -1);
    if (self_x < 0 || self_y < 0) {
        throw std::invalid_argument("--chiplet-onnx requires non-negative NPU coordinates");
    }
    const std::string model_path = argv[4];
    const std::string cfg_path = getEnvString("NPUSIM_CONFIG", "npu_config.json");
    std::string topology_gv = getEnvString("NPUSIM_TOPOLOGY_GV", "");
    std::string report_directory = getEnvString("NPUSIM_REPORT_DIR", "reports");
    int node_count = parseIntArg(std::getenv("NPUSIM_NODE_COUNT"), 0);
    bool intra_delay_override_set = false;
    bool intra_delay_enable = false;
    parseCommonOverrides(5,
                         argc,
                         argv,
                         topology_gv,
                         node_count,
                         intra_delay_override_set,
                         intra_delay_enable,
                         &report_directory);

    NPUSim::NPUConfig cfg = NPUSim::loadConfig(cfg_path);
    applyTopologyOverride(cfg, topology_gv, node_count);
    if (!cfg.external_memory_enable || cfg.external_memory_model != "chiplet") {
        throw std::runtime_error(
            "--chiplet-onnx requires external_memory.enable=true and external_memory.model=chiplet");
    }
    if (cfg.dram_chiplet_region_bytes < 2) {
        throw std::runtime_error("--chiplet-onnx requires a DRAM chiplet region of at least two bytes");
    }

    // The graph-level lowerer carries physical DMA addresses.  Give every NPU
    // a private region, split into activation and weight halves, so several
    // NPU processes can run the same model concurrently without address
    // aliasing.
    const std::uint64_t grid_cols = static_cast<std::uint64_t>(
        std::max(1, cfg.dram_chiplet_grid_cols));
    const std::uint64_t slot = static_cast<std::uint64_t>(self_x) * grid_cols +
                               static_cast<std::uint64_t>(self_y);
    if (slot > std::numeric_limits<std::uint64_t>::max() / cfg.dram_chiplet_region_bytes) {
        throw std::runtime_error("ONNX chiplet DRAM region index overflow");
    }
    const std::uint64_t region_base = slot * cfg.dram_chiplet_region_bytes;
    if (region_base > cfg.dram_size_bytes ||
        cfg.dram_chiplet_region_bytes > cfg.dram_size_bytes - region_base) {
        throw std::runtime_error("ONNX chiplet DRAM region is outside configured DRAM capacity");
    }
    NPUSim::OnnxEventLoweringOptions lowering_options;
    lowering_options.activation_base_address = region_base;
    lowering_options.weight_base_address =
        region_base + cfg.dram_chiplet_region_bytes / 2;
    lowering_options.address_alignment_bytes = std::max<std::uint64_t>(
        1, cfg.dram_transaction_bytes);

    const std::vector<char> model = readBinaryFile(model_path);
    const NPUSim::OnnxEventLoweringResult lowered =
        NPUSim::lowerOnnxBytesToProgramEvents(model, cfg, lowering_options);
    const std::uint64_t region_end = region_base + cfg.dram_chiplet_region_bytes;
    for (const NPUSim::NpuProgramEvent& event : lowered.events) {
        if (event.kind != NPUSim::NpuProgramEventKind::kDmaLoad &&
            event.kind != NPUSim::NpuProgramEventKind::kDmaStore) {
            continue;
        }
        if (event.address < region_base || event.address > region_end ||
            event.bytes > region_end - event.address) {
            throw std::runtime_error(
                "ONNX tensor placement exceeds this NPU's configured DRAM-chiplet region; "
                "increase external_memory.chiplet.region_bytes");
        }
    }

    NPUSim::ChipletNpuRuntimeOptions runtime_options;
    runtime_options.self_x = self_x;
    runtime_options.self_y = self_y;
    runtime_options.initial_cycle = 1;
    runtime_options.report_directory = report_directory;
    runtime_options.log_prefix = "[NPUSIM][ONNX-CHIPLET][DRAM]";
    NPUSim::ChipletNpuRuntime runtime(cfg, runtime_options);
    const EventCounts counts = countProgramEvents(lowered.events);

    std::cout << "[NPUSim ][ONNX-CHIPLET][BOOT] coord=(" << self_x << ',' << self_y
              << ") model=" << model_path
              << " events=" << lowered.events.size()
              << " dram=(" << cfg.dram_chiplet_x << ',' << cfg.dram_chiplet_y << ')'
              << std::endl;
    const NPUSim::NpuProgramScheduleResult schedule = runtime.scheduleProgram(lowered.events);
    runtime.shutdown();
    // DMA read/write commands add entries to bench.txt, but they do not by
    // themselves update LegoSim's global "Benchmark elapses" clock.  A pure
    // ONNX timing workload has no CPU result-return path to report that final
    // clock incidentally, so publish the completed NPU clock explicitly after
    // the last DRAM shutdown handshake.  This is a bookkeeping notification,
    // not another network packet and therefore cannot double-count PopNet.
    InterChiplet::sendCycleCmd(runtime.chipCycle());

    const std::string report_path = report_directory + "/npusim_onnx_chiplet_" +
                                    std::to_string(self_x) + "_" + std::to_string(self_y) +
                                    "_schedule.json";
    writeOnnxChipletScheduleReport(report_path,
                                   lowered,
                                   schedule,
                                   runtime.dramCompletions(),
                                   counts,
                                   self_x,
                                   self_y,
                                   runtime.chipCycle());
    std::cout << "[NPUSim ][ONNX-CHIPLET][DONE] coord=(" << self_x << ',' << self_y
              << ") npu_schedule_finish_cycle=" << schedule.finish_cycle
              << " external_memory_end_cycle=" << runtime.chipCycle()
              << " dma_finish_cycle=" << schedule.dma_finish_cycle
              << " external_finish_cycle=" << schedule.external_finish_cycle
              << " overall_finish_cycle=" << schedule.overall_finish_cycle
              << " dram_completions=" << runtime.dramCompletions().size()
              << " injected_intra_cycles=" << schedule.injected_intra_cycles
              << " transactions=" << (counts.dma_loads + counts.dma_stores)
              << " report=" << report_path << std::endl;
    return 0;
}

}  // namespace

int main(int argc, char* argv[]) {
    try {
        if (argc >= 2 && std::string(argv[1]) == "--local") {
            return runLocal(argc, argv);
        }
        if (argc >= 2 && std::string(argv[1]) == "--lower-events") {
            return runOnnxEventLowering(argc, argv);
        }
        if (argc >= 2 && std::string(argv[1]) == "--intra-bench") {
            return runOnnxIntraBench(argc, argv);
        }
        if (argc >= 2 && std::string(argv[1]) == "--chiplet-onnx") {
            return runOnnxChiplet(argc, argv);
        }
        if (argc >= 2 &&
            (std::string(argv[1]) == "--matmul" || std::string(argv[1]) == "--direct-matmul")) {
            return runDirectMatMul(argc, argv);
        }

        if (argc < 6) {
            std::cerr << "usage: npusim <idX> <idY> <peerX> <peerY> <cfg_path> --topology-gv <topology.gv>\n"
                      << "       npusim --local <model.onnx> [input0.txt] [input1.txt] "
                         "[--topology-gv path] [--node-count n] [--no-intra-delay|--intra-delay]\n"
                      << "       npusim --lower-events <model.onnx> "
                         "[--topology-gv path] [--node-count n]\n"
                      << "       npusim --intra-bench <model.onnx> "
                         "--topology-gv <path> [--node-count n]\n"
                      << "       npusim --chiplet-onnx <self_x> <self_y> <model.onnx> "
                         "--topology-gv <path> [--report-dir dir] [--node-count n]\n"
                      << "       npusim --matmul <rows_a> <cols_a> <cols_b> <input0.txt> <input1.txt> "
                         "[--topology-gv path] [--node-count n] [--no-intra-delay|--intra-delay]\n";
            return 1;
        }

        const int idx_x = std::atoi(argv[1]);
        const int idx_y = std::atoi(argv[2]);
        const int peer_x = std::atoi(argv[3]);
        const int peer_y = std::atoi(argv[4]);
        const std::string cfg_path = argv[5];
        std::string topology_gv = getEnvString("NPUSIM_TOPOLOGY_GV", "");
        int node_count = parseIntArg(std::getenv("NPUSIM_NODE_COUNT"), 0);
        bool intra_delay_override_set = false;
        bool intra_delay_enable =
            getEnvBool("NPUSIM_INTRA_DELAY_ENABLE", true, &intra_delay_override_set);
        parseCommonOverrides(6,
                             argc,
                             argv,
                             topology_gv,
                             node_count,
                             intra_delay_override_set,
                             intra_delay_enable);
        const std::string bench_path = getEnvString("NPUSIM_BENCH", "bench.txt");
        const std::string delay_path = getEnvString("NPUSIM_DELAY_PROFILE", "reports/npu_intra_delay_profile.txt");
        const std::string report_path = getEnvString("NPUSIM_REPORT", "reports/npu_report.json");

        NPUSim::NPUConfig cfg = NPUSim::loadConfig(cfg_path);
        applyTopologyOverride(cfg, topology_gv, node_count);
        if (intra_delay_override_set) {
            cfg.intra_delay_enable = intra_delay_enable;
        }
        unsigned long long chip_cycle = 0;
        int task_id = 1;

        std::cout << "[NPUSim ][BOOT] coord=(" << idx_x << "," << idx_y << ") peer=("
                  << peer_x << "," << peer_y << ") macs=" << cfg.mac_unit_count
                  << " sram_per_mac=" << cfg.sram_per_mac_bytes
                  << " cfg=" << cfg_path << std::endl;

        while (true) {
            std::vector<std::int64_t> msg(5, 0);
            std::cout << "[NPUSim ][WAIT] waiting command from peer..." << std::endl;
            receivePayload(peer_x, peer_y, idx_x, idx_y, msg.data(), msg.size(), chip_cycle);

            if (msg[0] == 0) {
                std::cout << "[NPUSim ][STOP] stop command received, chip_cycle="
                          << chip_cycle << std::endl;
                break;
            }
            if (msg[0] == 2) {
                const std::int64_t rows_a = msg[1];
                const std::int64_t cols_a = msg[2];
                const std::int64_t cols_b = msg[3];
                const std::uint64_t output_size =
                    static_cast<std::uint64_t>(std::max<std::int64_t>(0, msg[4]));
                if (rows_a <= 0 || cols_a <= 0 || cols_b <= 0) {
                    throw std::runtime_error("direct MatMul command has invalid dimensions");
                }

                std::vector<std::int64_t> input0(
                    static_cast<std::size_t>(rows_a * cols_a), 0);
                std::vector<std::int64_t> input1(
                    static_cast<std::size_t>(cols_a * cols_b), 0);
                std::int64_t start_signal = 0;

                std::cout << "[NPUSim ][TASK] #" << task_id
                          << " direct_op=MatMul rows_a=" << rows_a
                          << " cols_a=" << cols_a
                          << " cols_b=" << cols_b
                          << " output=" << output_size << std::endl;

                receivePayload(peer_x, peer_y, idx_x, idx_y, input0.data(), input0.size(), chip_cycle);
                receivePayload(peer_x, peer_y, idx_x, idx_y, input1.data(), input1.size(), chip_cycle);
                receivePayload(peer_x, peer_y, idx_x, idx_y, &start_signal, 1, chip_cycle);

                NPUSim::RunResult result =
                    NPUSim::runMatMulI64(input0,
                                         input1,
                                         rows_a,
                                         cols_a,
                                         cols_b,
                                         cfg,
                                         bench_path,
                                         delay_path,
                                         false,
                                         "direct_matmul");
                chip_cycle += result.total_cycles;
                NPUSim::writeJsonReport(report_path, result);

                std::vector<std::int64_t> output = result.output_i64;
                output.resize(static_cast<std::size_t>(output_size), 0);

                std::int64_t done = 1;
                sendPayload(idx_x, idx_y, peer_x, peer_y, &done, 1, chip_cycle);
                sendPayload(idx_x, idx_y, peer_x, peer_y, output.data(), output.size(), chip_cycle);

                std::cout << "[NPUSim ][DONE] #" << task_id
                          << " mode=direct"
                          << " output_elements=" << output.size()
                          << " model_cycles=" << result.total_cycles
                          << " injected_intra_cycles=" << result.injected_intra_cycles
                          << " ddr_bytes=" << (result.ddr_read_bytes + result.ddr_write_bytes)
                          << " dram_cycles=" << result.dram_cycles
                          << " chip_cycle=" << chip_cycle << std::endl;
                ++task_id;
                continue;
            }
            if (msg[0] != 1) {
                std::cout << "[NPUSim ][WARN] ignore unknown op=" << msg[0] << std::endl;
                continue;
            }

            const std::uint64_t input0_size = static_cast<std::uint64_t>(std::max<std::int64_t>(0, msg[1]));
            const std::uint64_t input1_size = static_cast<std::uint64_t>(std::max<std::int64_t>(0, msg[2]));
            const std::uint64_t output_size = static_cast<std::uint64_t>(std::max<std::int64_t>(0, msg[3]));
            const std::uint64_t model_size = static_cast<std::uint64_t>(std::max<std::int64_t>(0, msg[4]));

            std::cout << "[NPUSim ][TASK] #" << task_id
                      << " input0=" << input0_size
                      << " input1=" << input1_size
                      << " output=" << output_size
                      << " model=" << model_size << std::endl;

            std::vector<char> model(model_size, 0);
            std::vector<std::int64_t> input0(input0_size, 0);
            std::vector<std::int64_t> input1(input1_size, 0);
            std::int64_t start_signal = 0;

            receivePayload(peer_x, peer_y, idx_x, idx_y, model.data(), model.size(), chip_cycle);
            receivePayload(peer_x, peer_y, idx_x, idx_y, input0.data(), input0.size(), chip_cycle);
            receivePayload(peer_x, peer_y, idx_x, idx_y, input1.data(), input1.size(), chip_cycle);
            receivePayload(peer_x, peer_y, idx_x, idx_y, &start_signal, 1, chip_cycle);

            std::cout << "[NPUSim ][TASK] #" << task_id << " payload received, start="
                      << start_signal << std::endl;

            NPUSim::RunResult result =
                NPUSim::runModel(model, input0, input1, cfg, bench_path, delay_path, false);
            chip_cycle += result.total_cycles;
            NPUSim::writeJsonReport(report_path, result);

            std::vector<std::int64_t> output = result.output_i64;
            output.resize(static_cast<std::size_t>(output_size), 0);

            std::int64_t done = 1;
            sendPayload(idx_x, idx_y, peer_x, peer_y, &done, 1, chip_cycle);
            sendPayload(idx_x, idx_y, peer_x, peer_y, output.data(), output.size(), chip_cycle);

            std::cout << "[NPUSim ][DONE] #" << task_id
                      << " output_elements=" << output.size()
                      << " model_cycles=" << result.total_cycles
                      << " injected_intra_cycles=" << result.injected_intra_cycles
                      << " ddr_bytes=" << (result.ddr_read_bytes + result.ddr_write_bytes)
                      << " dram_cycles=" << result.dram_cycles
                      << " chip_cycle=" << chip_cycle << std::endl;
            ++task_id;
        }

        std::cout << "[NPUSim ][EXIT] process exiting." << std::endl;
        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "[NPUSim ][ERROR] " << ex.what() << std::endl;
        return 1;
    }
}

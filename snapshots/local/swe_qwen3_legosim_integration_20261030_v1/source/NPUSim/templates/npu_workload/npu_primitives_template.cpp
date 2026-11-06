#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "npusim_chiplet_runtime.h"
#include "npusim_runtime.h"
#include "sync_protocol.h"

namespace {

int parseCoordinate(const char* text, const char* name) {
    char* end = nullptr;
    const long value = std::strtol(text, &end, 10);
    if (end == text || *end != '\0' || value < 0 || value > 15) {
        throw std::runtime_error(std::string("invalid ") + name);
    }
    return static_cast<int>(value);
}

}  // namespace

NPUSim::NpuEventRecorder buildProgram(const NPUSim::NPUConfig& cfg) {
    // 这里描述“时序事件”，不是功能计算本身。若 workload 需要数值正确性，
    // 可在此文件或其他 C++ 文件实现普通功能模型，再保持本事件流与之对应。
    NPUSim::NpuEventRecorder recorder;
    constexpr std::uint64_t kBytes = 4096;
    // 同一个 op 编号表示一个逻辑 MAC 类算子；它会成为片内 profile 的 TASK 编号。
    // 不同逻辑算子请使用不同的非零 op 编号。
    constexpr std::uint64_t kOp = 100;

    // DMA 的 address 是 DRAM 芯粒中的逻辑地址，bytes 是本次访问的字节数。
    // dmaLoad 返回事件 ID；后续计算在依赖它时会等到数据真正从 DRAM 返回。
    const auto x = recorder.dmaLoad(kOp, 0x00100000, kBytes);
    const auto w = recorder.dmaLoad(kOp, 0x00200000, kBytes);

    // 示例：把 MatMul 类工作均分给所有 MAC。mac_id 必须小于 mac_unit_count；
    // 多个 MAC 事件可并行，但均依赖 x、w 的 DMA 完成。
    std::vector<NPUSim::NpuEventId> mac_done;
    for (int mac = 0; mac < cfg.mac_unit_count; ++mac) {
        mac_done.push_back(recorder.macCompute(kOp, 4096, mac, {x, w}));
    }
    const auto mac_join = recorder.barrier(kOp, mac_done);
    // vector/reduce 表示 MAC 后的激活、归约等工作。barrier 显式表达数据依赖，
    // 而不是依靠事件出现的文本顺序猜测依赖。
    const auto activation = recorder.vectorCompute(kOp, 4096, {mac_join});
    const auto reduction = recorder.reduceCompute(kOp, 1024, {activation});
    const auto output = recorder.vectorCompute(kOp, 4096, {activation, reduction});
    recorder.dmaStore(kOp, 0x00300000, kBytes, {output});
    return recorder;
}

int main(int argc, char* argv[]) {
    try {
        // make cpp-intra-bench 调用此模式。必须复用上方完全相同的 buildProgram()
        // 以保证离线片内 PopNet 的 TASK 编号与在线 phase1 运行时严格一致。
        // 此模式只写 controller<->MAC 的私有 bench，不访问 DRAM 芯粒。
        if (argc == 4 && std::string(argv[1]) == "--intra-bench") {
            const NPUSim::NPUConfig cfg = NPUSim::loadConfig(argv[2]);
            const NPUSim::NpuEventRecorder recorder = buildProgram(cfg);
            NPUSim::writeNpuProgramIntraBench(recorder.events(), cfg, argv[3]);
            std::cout << "[CPP-TEMPLATE][INTRA-BENCH] events=" << recorder.events().size()
                      << " bench=" << argv[3] << std::endl;
            return 0;
        }
        if (argc != 5) {
            std::cerr << "usage: npu_primitives_template <self_x> <self_y> <config.json> <report_dir>\n"
                         "       npu_primitives_template --intra-bench <config.json> <bench_npu_intra.txt>\n";
            return 1;
        }
        const int self_x = parseCoordinate(argv[1], "self_x");
        const int self_y = parseCoordinate(argv[2], "self_y");
        const NPUSim::NPUConfig cfg = NPUSim::loadConfig(argv[3]);

        NPUSim::ChipletNpuRuntimeOptions options;
        // 坐标必须与 cpp_chiplet.yml 中该 NPU phase1 进程的位置一致。
        options.self_x = self_x;
        options.self_y = self_y;
        options.report_directory = argv[4];
        options.intra_delay_profile_path = std::getenv("NPUSIM_INTRA_DELAY_PROFILE")
                                               ? std::getenv("NPUSIM_INTRA_DELAY_PROFILE")
                                               : "";
        options.log_prefix = "[CPP-TEMPLATE][DRAM]";
        NPUSim::ChipletNpuRuntime runtime(cfg, options);

        const NPUSim::NpuEventRecorder recorder = buildProgram(cfg);

        const NPUSim::NpuProgramScheduleResult schedule =
            runtime.scheduleProgram(recorder.events());
        // shutdown 告诉共享 DRAM server：该 NPU 已不再发送请求。
        runtime.shutdown();
        // 对纯 NPU workload 显式公布最终周期；否则 LegoSim 总周期可能保持为 0。
        InterChiplet::sendCycleCmd(runtime.chipCycle());

        std::cout << "[CPP-TEMPLATE][DONE] coord=(" << self_x << ',' << self_y
                  << ") finish_cycle=" << schedule.finish_cycle
                  << " injected_intra_cycles=" << schedule.injected_intra_cycles
                  << " events=" << recorder.events().size() << std::endl;
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "[CPP-TEMPLATE][ERROR] " << error.what() << std::endl;
        return 1;
    }
}

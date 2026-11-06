CXX ?= g++
PYTHON ?= python3
CMAKE ?= cmake
# 自动向上查找包含 NPUSim/ 的 LegoSim 根目录。标准交付位置是
# benchmark/my_npu_workload；如果模板放在仓库外，请显式传入
# SIMULATOR_ROOT=/path/to/LEGOSIM_MICRO。
SIMULATOR_ROOT ?= $(firstword $(foreach p,.. ../.. ../../.. ../../../.. ../../../../..,$(if $(wildcard $(p)/NPUSim),$(abspath $(p)))))
ifeq ($(strip $(SIMULATOR_ROOT)),)
$(error Cannot find LEGOSIM_MICRO root; run make SIMULATOR_ROOT=/path/to/LEGOSIM_MICRO)
endif
BENCHMARK_ROOT := $(abspath .)
INTERCHIPLET := $(SIMULATOR_ROOT)/interchiplet/bin/interchiplet
POPNET := $(SIMULATOR_ROOT)/popnet_chiplet/build/popnet
RAMULATOR_DIR := $(SIMULATOR_ROOT)/Ramulator2-Chiplet
NPUSIM_DIR := $(SIMULATOR_ROOT)/NPUSim
CONFIG := $(BENCHMARK_ROOT)/npu_chiplet_config.json
INTRA_TOPOLOGY := $(BENCHMARK_ROOT)/npusim_vertical_4_4.gv
INTRA_NODE_COUNT := 17
INTRA_MAC_COUNT := 16

CPP_BINARY := bin/npu_primitives_template
CPP_RUN_ROOT := $(BENCHMARK_ROOT)/output/cpp_run

# ONNX 与 C++ 原语应用共用同一份 NPU/DRAM 配置：CPU=(0,0)、NPU=(1,0)、
# DRAM=(2,0)。因此片间 PopNet/InterChiplet 的 mesh width 统一为 3。
# 修改芯粒坐标时，必须同时修改 config、对应 yml、拓扑 gv 和 LPDDR5 坐标。
CPU_ONNX_YML := $(BENCHMARK_ROOT)/cpu_onnx_chiplet.yml
CPU_ONNX_RUN_ROOT := $(BENCHMARK_ROOT)/output/cpu_onnx_run
CPU_ONNX_CPU_BINARY := bin/cpu_onnx_start
CPU_ONNX_WRAPPER_SOURCE := $(BENCHMARK_ROOT)/npu_onnx_chiplet_workload.cpp

COMMON_SOURCES := \
	$(NPUSIM_DIR)/npusim_runtime.cpp \
	$(NPUSIM_DIR)/npusim_chiplet_memory.cpp \
	$(NPUSIM_DIR)/npusim_chiplet_runtime.cpp
COMMON_FLAGS := -std=c++17 -O2 -Wall -Wextra \
	-I$(NPUSIM_DIR) \
	-I$(SIMULATOR_ROOT)/interchiplet/includes \
	-I$(SIMULATOR_ROOT)/artifact/MLP/json/include

.PHONY: all prepare require-interchiplet require-popnet require-ramulator tiny-onnx \
	cpp-intra-bench cpp-intra-delay cpp-run run \
	cpu-onnx-wrapper-build cpu-onnx-intra-bench cpu-onnx-intra-delay \
	onnx-run cpu-onnx-run clean

all: require-interchiplet $(CPP_BINARY)

# Ubuntu 服务器上的一次性准备：构建 InterChiplet、PopNet、Ramulator2 芯粒和官方
# ONNX/NPUSim 前端。后续运行目标不必重复手动执行。
prepare:
	$(CMAKE) -S $(SIMULATOR_ROOT)/interchiplet -B $(SIMULATOR_ROOT)/interchiplet/build
	$(CMAKE) --build $(SIMULATOR_ROOT)/interchiplet/build --parallel
	$(CMAKE) -S $(SIMULATOR_ROOT)/popnet_chiplet -B $(SIMULATOR_ROOT)/popnet_chiplet/build
	$(CMAKE) --build $(SIMULATOR_ROOT)/popnet_chiplet/build --parallel
	$(MAKE) -C $(RAMULATOR_DIR) SIMULATOR_ROOT=$(SIMULATOR_ROOT)
	$(MAKE) -C $(NPUSIM_DIR) build

require-interchiplet:
	@test -f $(SIMULATOR_ROOT)/interchiplet/lib/libinterchiplet_c.a -a -x $(INTERCHIPLET) || { echo "ERROR: run make prepare first (or build interchiplet)."; exit 1; }

require-popnet:
	@test -x $(POPNET) || { echo "ERROR: run make prepare first (or build popnet_chiplet)."; exit 1; }

require-ramulator:
	@test -x $(RAMULATOR_DIR)/ramulator2 || { echo "ERROR: run make prepare first (or build Ramulator2-Chiplet)."; exit 1; }

$(CPP_BINARY): npu_primitives_template.cpp $(COMMON_SOURCES)
	mkdir -p bin
	$(CXX) $(COMMON_FLAGS) $^ $(SIMULATOR_ROOT)/interchiplet/lib/libinterchiplet_c.a -o $@

# CPU 端只负责跨芯粒任务协议：发送 token=1，并等待 NPU 的完成状态。
$(CPU_ONNX_CPU_BINARY): cpu_onnx_start.cpp require-interchiplet
	mkdir -p bin
	$(CXX) -std=c++17 -O2 -Wall -Wextra \
		-I$(NPUSIM_DIR) \
		-I$(RAMULATOR_DIR) \
		-I$(SIMULATOR_ROOT)/interchiplet/includes \
		$< $(SIMULATOR_ROOT)/interchiplet/lib/libinterchiplet_c.a -o $@

# ONNX wrapper 依赖官方 ONNX/Protobuf，必须由 NPUSim CMake 目标链接；
# 不要直接用 g++ 编译 npu_onnx_chiplet_workload.cpp。
cpu-onnx-wrapper-build: require-interchiplet
	$(CMAKE) -S $(NPUSIM_DIR) -B $(NPUSIM_DIR)/build \
		-DCMAKE_BUILD_TYPE=Release \
		-DNPUSIM_ONNX_CHIPLET_WRAPPER_SOURCE=$(CPU_ONNX_WRAPPER_SOURCE)
	# 同时构建 npusim：下一步 cpu-onnx-intra-bench 需要用它导出片内 trace。
	$(CMAKE) --build $(NPUSIM_DIR)/build --target npusim npusim_onnx_chiplet_wrapper --parallel

# 生成内置 [1,2,8] RMSNorm -> MLA-like attention 小图。仅用于快速 ONNX
# smoke test，不能作为正式性能 benchmark。
tiny-onnx:
	$(PYTHON) $(BENCHMARK_ROOT)/generate_tiny_rmsnorm_mla_onnx.py

# 阶段 0（C++）：以完全相同的 buildProgram() 生成无片内延迟的私有 NPU trace。
# 此处不能读取旧 profile，否则会把上一次实验的延迟带入新的片内校准。
cpp-intra-bench: all require-popnet
	mkdir -p $(CPP_RUN_ROOT)/reports
	NPUSIM_INTRA_DELAY_ENABLE=0 $(CPP_BINARY) --intra-bench $(CONFIG) $(CPP_RUN_ROOT)/bench_npu_intra.txt

cpp-intra-delay: cpp-intra-bench
	# 片内 PopNet 回放并聚合为 TASK/MAC profile，供之后的在线 phase1 注入。
	SIMULATOR_ROOT=$(SIMULATOR_ROOT) NPUSIM_CONFIG=$(CONFIG) MAC_COUNT=$(INTRA_MAC_COUNT) NODE_COUNT=$(INTRA_NODE_COUNT) TOPO_FILE=$(INTRA_TOPOLOGY) BENCH_FILE=$(CPP_RUN_ROOT)/bench_npu_intra.txt DELAY_FILE=$(CPP_RUN_ROOT)/delayInfo_npu_intra.txt POPNET_LOG_FILE=$(CPP_RUN_ROOT)/popnet_npu_intra.log bash $(NPUSIM_DIR)/run_popnet_intra_npu.sh
	$(PYTHON) $(NPUSIM_DIR)/build_npu_intra_delay_profile.py --delay $(CPP_RUN_ROOT)/delayInfo_npu_intra.txt --out $(CPP_RUN_ROOT)/reports/npu_intra_delay_profile.txt --mac-count $(INTRA_MAC_COUNT) --config $(CONFIG)

# ONNX 片内离线阶段：只模拟 NPU controller<->MAC，不启动 CPU/DRAM chiplet。
# ONNX 图先 lower 为 DMA/MAC/VECTOR/REDUCE/BARRIER 事件，再得到私有
# bench_npu_intra.txt；片内 PopNet 输出随后聚合为 npu_intra_delay_profile.txt。
cpu-onnx-intra-bench: cpu-onnx-wrapper-build require-popnet
	@test -f $(BENCHMARK_ROOT)/model.onnx || { echo "ERROR: run make tiny-onnx or copy your model to $(BENCHMARK_ROOT)/model.onnx"; exit 1; }
	mkdir -p $(CPU_ONNX_RUN_ROOT)/reports
	NPUSIM_CONFIG=$(CONFIG) NPUSIM_BENCH=$(CPU_ONNX_RUN_ROOT)/bench_npu_intra.txt \
		$(NPUSIM_DIR)/build/npusim --intra-bench $(BENCHMARK_ROOT)/model.onnx \
		--topology-gv $(INTRA_TOPOLOGY) --node-count $(INTRA_NODE_COUNT)

cpu-onnx-intra-delay: cpu-onnx-intra-bench
	SIMULATOR_ROOT=$(SIMULATOR_ROOT) NPUSIM_CONFIG=$(CONFIG) \
		MAC_COUNT=$(INTRA_MAC_COUNT) NODE_COUNT=$(INTRA_NODE_COUNT) \
		TOPO_FILE=$(INTRA_TOPOLOGY) \
		BENCH_FILE=$(CPU_ONNX_RUN_ROOT)/bench_npu_intra.txt \
		DELAY_FILE=$(CPU_ONNX_RUN_ROOT)/delayInfo_npu_intra.txt \
		POPNET_LOG_FILE=$(CPU_ONNX_RUN_ROOT)/popnet_npu_intra.log \
		bash $(NPUSIM_DIR)/run_popnet_intra_npu.sh
	$(PYTHON) $(NPUSIM_DIR)/build_npu_intra_delay_profile.py \
		--delay $(CPU_ONNX_RUN_ROOT)/delayInfo_npu_intra.txt \
		--out $(CPU_ONNX_RUN_ROOT)/reports/npu_intra_delay_profile.txt \
		--mac-count $(INTRA_MAC_COUNT) --config $(CONFIG)

cpp-run run: cpp-intra-delay require-popnet require-ramulator
	# C++ 原语应用的在线 phase1/phase2：只做一次时序执行；全局 bench.txt 由 InterChiplet 写出。
	mkdir -p $(CPP_RUN_ROOT)/reports
	cd $(CPP_RUN_ROOT) && SIMULATOR_ROOT=$(SIMULATOR_ROOT) NPUSIM_INTRA_DELAY_PROFILE=$(CPP_RUN_ROOT)/reports/npu_intra_delay_profile.txt $(INTERCHIPLET) $(BENCHMARK_ROOT)/cpp_chiplet.yml -w 3 -f 4 -t 1
# 单轮诊断入口：CPU 先将输入写入 DRAM，再发送 token/descriptor 给 NPU；
# NPU lower+执行 ONNX，最后 CPU 从 DRAM 读取输出。
cpu-onnx-run: $(CPU_ONNX_CPU_BINARY) cpu-onnx-wrapper-build cpu-onnx-intra-delay require-popnet require-ramulator
	mkdir -p $(CPU_ONNX_RUN_ROOT)/reports
	cd $(CPU_ONNX_RUN_ROOT) && \
		SIMULATOR_ROOT=$(SIMULATOR_ROOT) \
		NPUSIM_NPU_TOPOLOGY=$(INTRA_TOPOLOGY) \
		NPUSIM_INTRA_DELAY_PROFILE=$(CPU_ONNX_RUN_ROOT)/reports/npu_intra_delay_profile.txt \
		$(INTERCHIPLET) $(CPU_ONNX_YML) -w 3 -f 4 -t 1

# ONNX 正式入口（推荐）：单轮执行，Ramulator2 负责 LPDDR5 延迟。
onnx-run: $(CPU_ONNX_CPU_BINARY) cpu-onnx-wrapper-build cpu-onnx-intra-delay require-popnet require-ramulator
	mkdir -p $(CPU_ONNX_RUN_ROOT)/reports
	cd $(CPU_ONNX_RUN_ROOT) && \
		SIMULATOR_ROOT=$(SIMULATOR_ROOT) \
		NPUSIM_NPU_TOPOLOGY=$(INTRA_TOPOLOGY) \
		NPUSIM_INTRA_DELAY_PROFILE=$(CPU_ONNX_RUN_ROOT)/reports/npu_intra_delay_profile.txt \
		$(INTERCHIPLET) $(CPU_ONNX_YML) -w 3 -f 4 -t 1

clean:
	rm -rf bin output

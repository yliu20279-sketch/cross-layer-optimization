CMAKE ?= cmake
PYTHON ?= python3
BUILD_DIR ?= build
BUILD_TYPE ?= Release
# Official ONNX compiles hundreds of translation units.  Keep the default
# deliberately conservative on shared Ubuntu servers; callers with known
# spare RAM can override it, e.g. `make build BUILD_JOBS=8`.
BUILD_JOBS ?= 2
CMAKE_ARGS ?=

ONNX_MODEL ?= model.onnx
INPUT0 ?=
INPUT1 ?=
CONFIG ?= npu_config.json
MAC_COUNT ?= 16
TOPOLOGY_GV ?=
NODE_COUNT ?=
INTRA_DELAY ?= 1
TEST_CONFIG ?= tests/fixtures/npu_chiplet_smoke_config.json
TEST_TOPOLOGY_GV ?= tests/fixtures/npu_vertical_4_4.gv
TEST_OUTPUT_DIR ?= output

.PHONY: all build configure require-topology-gv local lower-events chiplet-onnx bench delay smoke onnx-smoke onnx-lowering-smoke onnx-functional-smoke tensor-codec-smoke qwen-ops-smoke clean help

all: build

# The CMake project builds the checked-in official ONNX source, its generated
# protobuf code, and NPUSim in one dependency graph.  Do not replace this with
# a direct g++ link: libonnx has generated protobuf and transitive dependencies.
configure:
	$(CMAKE) -S . -B $(BUILD_DIR) -DCMAKE_BUILD_TYPE=$(BUILD_TYPE) $(CMAKE_ARGS)

build: configure
	$(CMAKE) --build $(BUILD_DIR) --target npusim --parallel $(BUILD_JOBS)

require-topology-gv:
	@if [ -z "$(TOPOLOGY_GV)" ]; then \
		echo "ERROR: TOPOLOGY_GV is required. NPUSim does not generate or default to a 4x4 topology."; \
		echo "Example: make local ONNX_MODEL=model.onnx TOPOLOGY_GV=topology/custom.gv"; \
		exit 1; \
	fi

local: build require-topology-gv
	NPUSIM_CONFIG=$(CONFIG) NPUSIM_TOPOLOGY_GV=$(TOPOLOGY_GV) NPUSIM_NODE_COUNT=$(NODE_COUNT) NPUSIM_INTRA_DELAY_ENABLE=$(INTRA_DELAY) ./$(BUILD_DIR)/npusim --local $(ONNX_MODEL) $(INPUT0) $(INPUT1)

lower-events: build require-topology-gv
	NPUSIM_CONFIG=$(CONFIG) NPUSIM_TOPOLOGY_GV=$(TOPOLOGY_GV) NPUSIM_NODE_COUNT=$(NODE_COUNT) ./$(BUILD_DIR)/npusim --lower-events $(ONNX_MODEL)

# Timing-only ONNX workload for an already-running LEGOSim phase1.  It lowers
# the graph and schedules it through ChipletNpuRuntime; the external LPDDR5
# chiplet is supplied by the benchmark phase1 YAML.
chiplet-onnx: build require-topology-gv
	@test -n "$(SELF_X)" && test -n "$(SELF_Y)" || { echo "ERROR: SELF_X and SELF_Y are required."; exit 1; }
	NPUSIM_CONFIG=$(CONFIG) NPUSIM_REPORT_DIR=$(REPORT_DIR) ./$(BUILD_DIR)/npusim --chiplet-onnx $(SELF_X) $(SELF_Y) $(ONNX_MODEL) --topology-gv $(TOPOLOGY_GV)

bench: build require-topology-gv
	NPUSIM_CONFIG=$(CONFIG) NPUSIM_TOPOLOGY_GV=$(TOPOLOGY_GV) NPUSIM_NODE_COUNT=$(NODE_COUNT) NPUSIM_INTRA_DELAY_ENABLE=0 NPUSIM_BENCH=bench.txt ./$(BUILD_DIR)/npusim --local $(ONNX_MODEL) $(INPUT0) $(INPUT1)

delay: bench require-topology-gv
	NPUSIM_CONFIG=$(CONFIG) MAC_COUNT=$(MAC_COUNT) NODE_COUNT=$(NODE_COUNT) TOPO_FILE=$(TOPOLOGY_GV) bash ./run_popnet_intra_npu.sh
	$(PYTHON) build_npu_intra_delay_profile.py --delay delayInfo_npu_intra.txt --out reports/npu_intra_delay_profile.txt --mac-count $(MAC_COUNT) --config $(CONFIG)

# Runtime and ONNX regression checks belong to NPUSim and use self-contained
# fixtures by default.  A benchmark may override TEST_CONFIG,
# TEST_TOPOLOGY_GV and TEST_OUTPUT_DIR to validate its own hardware setup.
smoke: build
	mkdir -p $(TEST_OUTPUT_DIR)
	$(CMAKE) --build $(BUILD_DIR) --target npusim_chiplet_smoke --parallel $(BUILD_JOBS)
	./$(BUILD_DIR)/npusim_chiplet_smoke $(TEST_CONFIG) $(TEST_TOPOLOGY_GV) $(TEST_OUTPUT_DIR)/chiplet_smoke_bench.txt $(TEST_OUTPUT_DIR)/chiplet_smoke_report.json

onnx-smoke: build
	mkdir -p $(TEST_OUTPUT_DIR)
	$(CMAKE) --build $(BUILD_DIR) --target npusim_onnx_matmul_smoke --parallel $(BUILD_JOBS)
	./$(BUILD_DIR)/npusim_onnx_matmul_smoke $(TEST_CONFIG) $(TEST_TOPOLOGY_GV) $(TEST_OUTPUT_DIR)/onnx_matmul_smoke_bench.txt

onnx-lowering-smoke: build
	$(CMAKE) --build $(BUILD_DIR) --target npusim_onnx_event_lowering_smoke --parallel $(BUILD_JOBS)
	./$(BUILD_DIR)/npusim_onnx_event_lowering_smoke $(TEST_CONFIG) $(TEST_TOPOLOGY_GV)

onnx-functional-smoke: build
	$(CMAKE) --build $(BUILD_DIR) --target npusim_onnx_functional_smoke --parallel $(BUILD_JOBS)
	./$(BUILD_DIR)/npusim_onnx_functional_smoke

tensor-codec-smoke: configure
	$(CMAKE) --build $(BUILD_DIR) --target npusim_tensor_codec_smoke --parallel $(BUILD_JOBS)
	./$(BUILD_DIR)/npusim_tensor_codec_smoke

qwen-ops-smoke: build
	$(CMAKE) --build $(BUILD_DIR) --target npusim_qwen_ops_smoke --parallel $(BUILD_JOBS)
	./$(BUILD_DIR)/npusim_qwen_ops_smoke $(TEST_CONFIG) $(TEST_TOPOLOGY_GV)

clean:
	rm -rf $(BUILD_DIR) bench.txt delayInfo_npu_intra.txt run_popnet_intra_npu.log reports

help:
	@echo "NPUSim Makefile (official ONNX C++ frontend)"
	@echo "  make build [BUILD_JOBS=2]"
	@echo "  make local ONNX_MODEL=model.onnx INPUT0=input0.txt INPUT1=input1.txt TOPOLOGY_GV=topology/custom.gv"
	@echo "  make lower-events ONNX_MODEL=model.onnx TOPOLOGY_GV=topology/custom.gv"
	@echo "  make chiplet-onnx ONNX_MODEL=model.onnx CONFIG=npu_config.json TOPOLOGY_GV=topology/custom.gv SELF_X=0 SELF_Y=0 [REPORT_DIR=reports]"
	@echo "  make bench ...; make delay ..."
	@echo "  make smoke|onnx-smoke|onnx-lowering-smoke|onnx-functional-smoke|tensor-codec-smoke|qwen-ops-smoke [TEST_CONFIG=...] [TEST_TOPOLOGY_GV=...]"
	@echo "  python3 build_memory_timing_profile.py --delay ... --transactions ... --dram-trace ... --out ...  # offline analysis only; do not feed back into NPUSim cycles"

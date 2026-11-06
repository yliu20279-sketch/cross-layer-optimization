# NPUSim

NPUSim 是 LEGOSim 的 NPU 芯粒 timing runtime。提供了两种输入方式：

1. ONNX：导出静态 shape、无 external_data 的 model.onnx；
2. C++：保留功能代码，并用六类原语描述 NPU timing。

## 克隆第三方库ONNX
~~~bash
cd NPUSim
git clone git@github.com:onnx/onnx.git
~~~

## 克隆并构建Ramulator2
~~~bash
cd LEGOSIM_MICRO
source setup_env.sh
git clone https://github.com/CMU-SAFARI/ramulator2.git \
  "$SIMULATOR_ROOT/ramulator2"

git -C "$SIMULATOR_ROOT/ramulator2" checkout \
  b30320bc9385b708e86b67ebb9f48858cc66d798

mkdir -p "$SIMULATOR_ROOT/ramulator2/build"
cd "$SIMULATOR_ROOT/ramulator2/build"

cmake .. -DRAMULATOR_PYTHON_BINDINGS=OFF
cmake --build . --parallel 2

~~~
## 安装 Ramulator2 Chiplet
~~~bash
export INTEGRATION_ROOT=/path/to/LegoSim-Ramulator2-Integration

cp -a \
  "$SIMULATOR_ROOT/NPUSim/changed_files/Ramulator2-Chiplet" \
  "$SIMULATOR_ROOT/"

make -C "$SIMULATOR_ROOT/Ramulator2-Chiplet" \
  SIMULATOR_ROOT="$SIMULATOR_ROOT" \
  -j2

mkdir -p "$SIMULATOR_ROOT/Ramulator2-Chiplet/reports"
~~~

## 编译 NPUSim和interchiplet
在 Ubuntu 服务器执行：

~~~bash
cd NPUSim
make build

# NPUSim/changed_files 目录下文件替换掉 interchiplet/ 目录对应的文件。
cd ../interchiplet
rm -rf build
cd build
cmake ..
make -j4
~~~

## 使用样例
NPUSim使用的模板：
~~~bash
cd LEGOSIM_MICRO/NPUSim
cp -r templates/npu_workload ../benchmark/my_npu_workload
cd ../benchmark/my_npu_workload
make prepare
# ONNX图需要自行生成并放入 model.onnx；可以用generate_tiny_rmsnorm_mla_onnx.py创建样例
make onnx-run
~~~

模板会启动 NPU、LPDDR5 chiplet 和一次 PopNet phase 2，输出都在 output/。具体解释可查看模板下的README.md。



## ONNX 输入

先检查 ONNX 是否能 lowering：

~~~bash
cd NPUSim
make lower-events \
  ONNX_MODEL=/path/to/model.onnx \
  CONFIG=npu_config.json \
  TOPOLOGY_GV=/path/to/npu_topology.gv \
  NODE_COUNT=17
~~~

该命令只做解析、lowering 和解析式 DDR timing，不启动 InterChiplet、
Ramulator2 或 PopNet。

在 LEGOSim phase-1 YAML 中使用 --chiplet-onnx 后，NPUSim 自动执行：

~~~text
ONNX -> DMA/MAC/VECTOR/REDUCE/BARRIER
     -> ChipletNpuRuntime::scheduleProgram()
     -> InterChiplet -> PopNet -> Ramulator2-Chiplet
     -> completion 依赖推进后续 NPU event
~~~

当前 timing lowering 支持 MatMul、Gemm、Conv、Softmax、LogSoftmax、
RMS/LayerNorm、Reduce*、常见逐元素/激活/cast/量化算子，以及 Transpose、
Concat、Reshape、Flatten、Identity、Dropout、Constant。不支持的算子或缺失/
动态 shape 会明确报错。

这是 timing 路径，不执行 ONNX 数值推理。具体边界见
[README_ONNX_EVENT_LOWERING.md](README_ONNX_EVENT_LOWERING.md)。

## C++ 原语输入

NPUSim 不会从任意 C++ 循环自动推断硬件行为。用户自己写功能代码，再记录：

~~~cpp
NPUSim::NpuEventRecorder recorder;
const auto a = recorder.dmaLoad(100, 0x00100000, bytes);
const auto b = recorder.dmaLoad(100, 0x00200000, bytes);
const auto mac = recorder.macCompute(100, ops, 0, {a, b});
const auto done = recorder.barrier(100, {mac});
recorder.dmaStore(100, 0x00300000, bytes, {done});
~~~

六类 API：

- dmaLoad / dmaStore：外部内存访问；
- macCompute：一个 MAC 上的乘加；
- vectorCompute：逐元素、激活、layout 等；
- reduceCompute：归约；
- barrier：汇合依赖。

在 chiplet workload 中调用：

~~~cpp
NPUSim::ChipletNpuRuntime runtime(config, options);
runtime.scheduleProgram(recorder.events());
runtime.shutdown();
InterChiplet::sendCycleCmd(runtime.chipCycle());
~~~

DMA 完成周期会自动限制后续事件。可直接编辑模板中的
[npu_primitives_template.cpp](templates/npu_workload/npu_primitives_template.cpp)。

## Timing Split

NPUSim 现在只保留片内计算、片内 DMA 端口时序，以及 completion 依赖的调度语义。
外部 LPDDR5 的服务时间由 LEGOSim 的联合仿真链路单独决定：

```text
NPUSim issueRequest()
  -> InterChiplet
  -> PopNet
  -> Ramulator2-Chiplet
  -> return completion
  -> ChipletNpuRuntime::scheduleProgram()
```

`wait_request_ids` 只表达 event 之间的完成依赖，不会替代这条联合仿真链路。

baseline 会生成：

~~~text
bench.txt
delayInfo.txt
reports/npusim_dram_transactions_X_Y.csv
reports/ramulator2_lpddr5_timing.csv
~~~

这里的 `dram` 仍表示共享外部内存地址空间；在 chiplet 模式下，实际后端是
Ramulator2 LPDDR5 芯粒。

注意：flit_payload_bytes 是 NPUSim 内部/片内粒度，区别LEGOSIM第二阶段的芯粒间网络flit。

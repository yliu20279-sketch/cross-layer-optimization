# ONNX 到 NPUSim 通用事件的 Lowering

`onnx_event_lowering.{h,cpp}` 是 ONNX 计算图与 NPUSim 通用事件运行时之间的编译边界。
它只负责解析图和生成事件，不执行张量数值，也不会自行启动 PopNet 或 Ramulator2。

```text
ONNX 字节流 -> parseOnnxModel -> Model -> lowerOnnx*ToProgramEvents
         -> DMA / MAC / VECTOR / REDUCE / BARRIER 事件
         -> ChipletNpuRuntime::scheduleProgram(...)（芯粒模式）
```

可用下面的命令仅检查解析、lowering 和解析式 DDR 时序：

```bash
cd NPUSim
NPUSIM_CONFIG=npu_config.json \
./build/npusim --lower-events model.onnx --topology-gv topology/custom.gv
```

没有提供 DRAM 回调时，该命令采用配置中的 DDR 带宽估算 DMA 时间。正式的
LegoSim workload 应把同一份事件表交给
`ChipletNpuRuntime::scheduleProgram()`；此时 DRAM 芯粒运行时为每个 DMA
请求返回绝对完成周期，并推进唯一的 NPU phase1 时钟。

## 完整的芯粒 timing 执行

`--lower-events` 只是检查命令，**不会**启动 InterChiplet、Ramulator2 或 PopNet。
在已经由 LegoSim 启动的 phase1 中，需要使用内置执行模式：

```bash
NPUSIM_CONFIG=npu_chiplet.json \
NPUSIM_REPORT_DIR=output/reports \
NPUSIM_INTRA_DELAY_PROFILE=output/reports/npu_intra_delay_profile.txt \
./build/npusim --chiplet-onnx 0 0 model.onnx \
  --topology-gv topology/custom.gv
```

该命令自动执行：

```text
官方 ONNX 解析 -> 通用事件 lowering
  -> ChipletNpuRuntime::scheduleProgram(events)
  -> 每个 DMA 请求/响应经 InterChiplet 访问配置中的 DRAM 芯粒
  -> DMA 的绝对完成周期限制依赖它的 MAC/vector/reduce 事件
  -> 生成每个 NPU 的 transaction CSV 与 schedule JSON
  -> 发送 DRAM server shutdown 标记
  -> 发送最终 CYCLE 通知，使 LegoSim benchmark 总周期非零
```

此模式仅做 timing，不执行 ONNX 的张量数值，也不实现 CPU 输入/输出 payload
协议。因此它适用于“ONNX 图到芯粒时序”的快速实验；若需要数值正确性，仍需由
C++ workload 或框架侧保留功能执行路径。

## CPU/NPU 协同入口

当 ONNX NPU 不是独立启动，而是由 CPU 下发任务并把完成结果返回 CPU 时，需要增加
一个很薄的 C++ 通信 wrapper；这不意味着用户必须手写 ONNX 算子原语。模板目录
`templates/npu_workload/` 已提供完整例子：

```bash
cd benchmark/my_npu_workload
make tiny-onnx       # 可选：生成很小的 ONNX smoke 图
make cpu-onnx-run
```

该例中 CPU `(0,0)` 发送任务描述符和 typed 输入 tensor 给 NPU `(1,0)`；NPU 收到后调用
`lowerOnnxBytesToProgramEvents()` 和 `ChipletNpuRuntime::scheduleProgram()`，再返回
completion、输出 tensor 元数据与 typed payload 给 CPU。NPU 的 DMA 仍访问 DRAM `(2,0)`，
所有 CPU↔NPU 与 NPU↔DRAM 通信都由 phase1 写进全局 `bench.txt`，再由 phase2 PopNet 回放。

模板 wrapper 已将 `runOnnxFunctionally()` 的 typed 输出按
`completion -> tensor descriptor -> shape -> payload` 回传给 CPU，并与
`scheduleProgram()` 的完成周期汇合：功能结果或 timing 任一未完成都不会提前发送。
功能路径在宿主机并行运行，但其 wall-clock 时间不折算为模拟 cycle；这样“时序慢于
功能”时会等待时序，而“功能尚未生成 tensor”时不会发送不存在的数据。输出的第一笔
CPU↔NPU write 以 timing finish cycle 作为 issue cycle；之后 descriptor/shape/payload
的传输自然继续推进全局模拟时钟。

该功能参考执行器覆盖当前模板小图所需的 MatMul、逐元素、Reduce、Sqrt、Reciprocal、
Softmax 和 Transpose 等路径；它不是完整 ONNX Runtime。生产模型出现不支持的功能算子
时会明确报错，应补全 `runOnnxFunctionally()` 的算子实现或在 wrapper 中接 ONNX Runtime。

当前执行路径只由本轮事件依赖、片内 PopNet 和外部 LPDDR5 访问共同决定，不再从上一轮
profile 反向注入 stall。

## dtype、量化与转换

模板的 `TensorDescriptor.dtype` 是稳定线协议：`1=fp32`（4 B）、`2=fp16`（2 B）、
`3=bf16`（2 B）。`npusim_tensor_codec.h` 负责小端 payload 编码/解码与 FP32↔FP16/BF16
round-to-nearest-even 转换，所以 phase1 中 CPU↔NPU 的 `bench.txt` 使用真实 payload
字节数。

在 NPU JSON 为 `activation/weight/accumulator/output` 同时配置 `*_bytes` 和
`*_dtype`。ONNX CPU/NPU wrapper 会拒绝缺失字段或二者冲突；旧纯 timing 配置可仍只使用
byte width。功能路径仍使用 host FP32 算术，但对输入、权重、
每个算子输出（`functional_round_each_operator`）和最终输出按配置舍入。这是存储/传输
精度模型；当前 `MatMul`/`Gemm`/`Conv` 已按 `accumulator_dtype` 在每次 MAC 累加后
舍入，其余算子仍是算子边界舍入。若需所有算子的严格位精确语义，仍需为每类算子定义
逐指令截断/饱和规则。

Ubuntu 检查：

```bash
make -C NPUSim tensor-codec-smoke
```

## 当前 Lowering 规则

- `MatMul`、`Gemm`、`Conv`：输入 DMA、分发到各 MAC 的 `MAC_COMPUTE`、barrier、
  可选的尾部 vector 处理、输出 DMA。
- `Softmax` / `LogSoftmax`：vector shift、reduce max、vector exp、reduce sum、
  最后一次 vector 归一化。
- `RMSNormalization`、`LayerNormalization`、`Reduce*`：生成 vector/reduce 事件序列。
- 逐元素算子（`Add`、`Mul`、`Div`、`Pow`、激活、cast、量化）：生成 vector 事件。
- `Identity`、`Dropout`、`Reshape`、`Flatten`：仅建立地址/ready 别名，不凭空生成
  计算或访存事件。

Lowerer 能对 MatMul/Gemm broadcasting、NCHW/OIHW Conv、逐元素广播、Reshape、
Flatten、Transpose、Concat 和 reduction 等常见路径做静态 shape 推导。默认情况下，
不支持的算子、缺失 shape 或动态维度都会明确报错。这是刻意设计：时序模型不能把
未知计算图区域静默当作零周期。

## 访存语义与当前边界

每个非 view 算子都将输出 materialize 到 activation 地址空间；其消费者会对该地址
生成 DMA load，并依赖生产者的 DMA store 完成事件。initializer 和 `Constant` 使用
weight 地址空间。这是一种保守的图级访存模型，适合首次接入 LPDDR5 芯粒和 phase2
时序。

当前尚未实现：任意算子的 SRAM 生命周期分配、任意算子的 tile 级 lowering、
multi-outstanding DMA。这些能力应作为 `OnnxEventLoweringResult` 后续 pass 来扩展，
而不是把各算子的 timing 代码重新写入某个 C++ workload。

标准 phase1 集成方式如下：

```cpp
#include "npusim_chiplet_runtime.h"

const auto lowered = NPUSim::lowerOnnxBytesToProgramEvents(model_bytes, cfg);
NPUSim::ChipletNpuRuntimeOptions options;
options.self_x = self_x;
options.self_y = self_y;
options.report_directory = report_dir;
options.intra_delay_profile_path = intra_profile_path;
NPUSim::ChipletNpuRuntime npu(cfg, options);
const auto schedule = npu.scheduleProgram(lowered.events);
// schedule.finish_cycle 即此次程序的完成周期；依赖事件已观察到
// 片内 PopNet delay 和外部 LPDDR5 访问对 data-ready 的影响。
```

以上代码不会把该事件路径变成 ONNX 数值执行器：实时张量数值和 CPU/IO 输入输出协议
仍由 workload 自己负责。

## 官方 ONNX 前端与构建

`NPUSim/onnx/` 下的仓库由 `NPUSim/CMakeLists.txt` 作为官方 ONNX C++/Protobuf
前端构建。`onnx_official_parser.cpp` 调用 `ModelProto::ParseFromArray` 和官方 ONNX
shape-inference API，再把通过验证的图转换为 NPUSim 精简的 `Model` 接口。旧的手写
protobuf/DOT 风格 tokenizer 已从运行时路径移除。

在 Ubuntu 服务器构建：

```bash
make -C NPUSim build
```

内置 ONNX 要求 CMake 3.26+ 和正常的 C++/Protobuf 工具链。NPUSim 默认
`BUILD_JOBS=2`，因为官方 ONNX 源码树编译占用内存较大；服务器内存充足时才提高：

```bash
make -C NPUSim build BUILD_JOBS=8
```

如果编译器或依赖环境发生较大变化，应清理 CMake cache 后重新配置：

```bash
cd NPUSim
rm -rf build
make build BUILD_JOBS=2
```

当前字节流前端会拒绝 ONNX `external_data` tensor。请先将模型 materialize 为包含
全部权重的单个 `.onnx` 文件；否则相对路径权重会使芯粒实验不可复现。将来可增加
基于文件路径的前端，并在实验 manifest 中记录解析后的权重文件。

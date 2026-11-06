# swe_qwen3：softmax/Top8目标CPU功能验证

日期：2026-10-27。结论分别是PASS_LIMITED_TOP8_GPU_ID_SLOT_WEIGHT_IDENTITY、PASS_LIMITED_HOST_CPU_ROUTE_OUTPUTS，以及PARTIAL_SOFTMAX_FP32_GPU_NOT_EXACT。没有整体GPU逐位数值或NPU原生TopK认证。

## 已完成

复用两个固定既有请求：短R0002与v6开发R0001的7个层0阶段，共759 token行。fixture SHA及运行前冻结通过；没有新GPU模型/agent/SWE任务或新留出访问。759是相关token行，不是759独立任务。BF16及host128GiB/HB8GiB不变。

独立C++实现保持FP32 softmax与归一化、int64 ID和最后BF16 codec边界。Top8实现按固定CUDA backend的阈值gather与32-slot排序语义实现，不调用torch.topk，不输入记录ID，不用自定稳定expert-ID排序覆盖源规则。理由及原始源码链接见TARGET_FUNCTIONAL_CONTRACT.md。

| 比较 | 结果 |
|---|---|
| 捕获GPU FP32概率→新Top8 | 759/759行ID、slot顺序及BF16权重逐位一致 |
| 捕获BF16 logits→新softmax/Top8 | 759/759行最终ID、slot及BF16权重逐位一致 |
| 新softmax FP32概率→GPU记录 | 7阶段均非逐位一致，最大绝对差1.4901161193847656e-7 |
| 按专家ID稳定排序负对照 | 151行与源GPU slot顺序不同 |
| 可选host路由适配器 | 759行输出及dtype检查通过，旧适配器不改 |

来源：attempt1/RESULTS.json、INDEPENDENT_AUDIT.json、ADAPTER_CHECK.json；验证器重新读取原fixture作为独立期望，而非只比较两次相同实现。

平局覆盖：486行非平局、206行内部平局、80行第8/9名边界平局，其中13行同时有内部与边界平局。独立审计核对每行8个唯一合法ID、所有strict winner、边界equal补足集合以及精确slot/weight。与此前CPU torch.topk边界集合不同的问题分开：本轮选择器已经在这些原输入上复现GPU集合与顺序，但上游目标GEMM若改变logits，不能据此保证全模型路由相同。

5个合成例包含uniform、内部平局、边界大组、underflow、signed-zero logits；验证合法集合、重复性和有限值。NaN/Inf logits、负概率与负零概率4项拒绝。没有新GPU合成oracle，合成例不是额外GPU数值认证。

另有两个固定CPU语义反例：不同BF16 logits经过FP32 exp舍入或下溢后变成相等概率，此时直接Top8(logits)选择的专家集合与完整softmax后选择不同。这排除了“利用实数单调性省略softmax再Top8”的不安全替换。来源：attempt1/PROBABILITY_TIE_PROBES.json；无额外GPU oracle。

## 目标架构路径

这是显式host x86软件回退，非NPU新增指令。一次Sniper ROI运行了实际完整内核，输入只有BF16 logits，输出IDs和BF16 weights再与记录逐字节核对，759行全部一致。

实际解析的CPU为4核2.5GHz、32/32KiB L1、256KiB L2、8MiB L3；gainestown-derived interval及12.8GB/s/60ns constant DRAM代理沿上阶段，不冒称物理校准。CPU应用单线程；其他核idle不能当4核吞吐。

该合并冷ROI共18418906条指令、9288362个2.5GHz周期；ROI3715344.8ns，其中nonidle3676674.8ns、idle38670ns。数据是759行合并批次，不是每turn自然到达；不除以759当在线单token成本，不把CPU周期当1ns NPU周期，不与GPU时间作加速比。该ROI没有CPU-NPU metadata搬移、NoC或NPU exp/TopK时序。来源：roi_attempt1/METRICS.json、sim/sim.out、sim.cfg、sim.stats.sqlite3、COMMAND.json、STATUS.json。

可复用入口route_adapter.py在CPU接收BF16 logits，返回FP32 probabilities、int64 selected、BF16 weights，并单独记录host功能事件。独立函数没有加载全模型；原BF16权重/适配器及所有旧失败不改。

## 仍然保留的失败

虽然最终路由输出全部相等，FP32中间概率仍失败，不能只比较最终BF16后宣布完整子链PASS。exp实现、归约顺序和除法舍入都是合理候选原因，当前尚未逐项隔离到原GPU中间指令；没有擅自提高模型精度、修改softmax早舍入或放宽容差。

有限域为E128/k8、有限BF16 logits和FP32非负标准概率。源GPU排序版本、尺寸、NaN/Inf、非标准negative-zero概率等边界不能外推；跨版本升级需要重新绑定。

下游接口的逻辑metadata为每token80 B，搬移和HB/NoC完成门控仍待接入；上阶段hostcodec/链路框架可复用。传输入口两种情形及避免重复D2H的规则在TARGET_FUNCTIONAL_CONTRACT.md固定。实际新输出可供已验输入范围的dispatch接口试接，不能据此提升整模型准入。

## 执行与交付

本轮新Sniper ROI1次，新增NPUSim片段0；本线NPUSim片段累计3、Sniper ROI累计3，物理NPU0。没有训练、W4/FP16替换、GPU推理/微测、SWE新任务或新留出正文访问。SWE修复评分没有作为本线门槛。

源身份：PyTorch2.6.0+cu124、git2236df1770800ffea5697b11b0bb0d910b2e59e1，CUDA12.4；安装的SortUtils/SortingCommon/Sort.h实际SHA见独立审计。运行前PROTOCOL/PRE_RUN_FREEZE与ROI_FREEZE未变。

证据包含代码、原输入/参考路由、实际输出、独立审计及完整Sniper统计；不含SWE gold patch或隐藏测试。DELIVERY.json/FILE_MANIFEST.json及本地LOCAL_DELIVERY_VERIFICATION.json分别记录封包与逐SHA回执。

来源：TARGET_FUNCTIONAL_CONTRACT.md列出的官方固定CUDA源码；../swe_qwen3_bf16_functional_v1_20261026/NUMERIC_CONTRACT.md、../swe_qwen3_host_boundary_20261027_v1/REPORT.md；全部机器结果在attempt1和roi_attempt1。

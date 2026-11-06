# 两模型P0-1b：同状态完整层与物理页迁移 v5

更新：2026-11-03（Asia/Shanghai）；目录沿用11月2日任务名。**状态仍为PARTIAL。**本轮补齐了单层诊断范围内的数据流连接与实际页迁移，未完成并行调度及完整成本准入，未启动正式性能实验。

## 1. 与v4相比，本轮实际补了什么

v4的CPU功能结果与独立Ramulator/PopNet时序是分离路径。v5将数值SRAM primitive、实际DRAM读写回调及NoC载荷完成放入同一进程状态：primitive读取实际HB数值，只有读回调完成才计算，输出写回完成后才供消费者使用；NoC接收后实际写入目的HB。

已连接完整单层：input RMSNorm→TP Q/K/V（含Qwen1.5 bias、Qwen3 Q/K norm）→RoPE→实际KV追加→QK/softmax/PV→O分片→SRS→残差/postnorm→自主router→EP专家及shared TP→专家编号顺序加权合并→残差→SAG。

两模型各执行prefill 1 token和cached decode 1 token。输入是固定诊断隐藏态，不是自然benchmark数据或完整语言模型生成。最终运行在prefill后按固定规则交换两页权重，decode实际使用新物理地址。该交换不是学习得到的CA布局，不产生性能收益结论。

来源：[Qwen3最终回执](remote_review/runs/qwen3_layer02/RESULT.json)、[Qwen1.5最终回执](remote_review/runs/qwen15_layer02/RESULT.json)、[实际构建身份](remote_review/evidence/COUPLED_BUILD_04.json)。

## 2. 本轮发现并修正的三项错误或不一致

1. **Qwen1.5的实际config是`norm_topk_prob=false`。**v4功能入口对两模型都做了TopK归一化，改变了Qwen1.5的概率质量；已按实际config修正，Qwen3仍为true。旧v4回执保留为接口范围，不能作为原模型数值通过依据。
2. 官方Transformers 4.51.3的两模型MoE按专家编号执行`index_add`。早期候选按TopK槽位累加，16位舍入可能不同；最终改为按专家编号合并，路由槽位及对应权重身份不变。
3. 早期v5将原BF16 FDA64 primitive用于FP16扩展操作数，不符合原FP16 K64分块合同。最终显式分离：Qwen3保留BF16 FDA64；Qwen1.5采用K64内递增K的FP32部分和、再递增K合并。有限FP16反例在同后端分别产生1与2，确认两条路径未混淆。

这些是精度/语义绑定修正，不是按性能结果调整输入或挑选参数。原始版本、失败和对照保留。

来源：[实际Qwen1.5 config](upstream/qwen15_config.json)、[实际Qwen3 config](upstream/qwen3_config.json)、[路由修正记录](evidence/ROUTER_NORMALIZATION_CORRECTION.json)、[累加修正记录](evidence/ACCUMULATION_CORRECTIONS.json)、[精度反例](remote_review/evidence/PRECISION_CONTRACT_PROBE.json)、[官方MoE代码快照](remote_review/runs/qwen15_layer02/independent_cpu_reference/MOE_FORWARD_SOURCE.txt)。

## 3. 最终有限执行与独立原日志审计

| 项目 | Qwen3 BF16 | Qwen1.5 GPTQ解码FP16 |
|---|---:|---:|
| 层/阶段 | 层0，prefill1＋decode1 | 同左 |
| 功能/载荷几何 | TP16/EP16 | TP4/EP4，PP阶段0 |
| 实际DRAM事务及匹配回调 | 5,531,540 | 7,501,408 |
| 实际NoC包及匹配完成 | 952 | 296 |
| primitive作业 | 662 | 266 |
| 分配与释放 | 4217/4217 | 1673/1673 |
| 独立验证KV旧前缀的载荷数 | 32 | 8 |
| 本次最大单分区HB预留 | 28,340,224 B | 89,161,728 B |
| 实际迁移读/写 | 各8192 B | 各8192 B |

以上是同一模拟器状态中的实际有限执行计数，不是物理芯片测量。驱动串行调用各rank，**不能将TP/EP几何覆盖写成并行性能基线通过**。

独立脚本逐行检查原始事件：issue/callback身份、时间、有效范围、实际页地址、内存分配不别名、代际、释放及KV前缀；读取指纹与已完成写入逐窗口一致，无未匹配窗口。FNV64仅用于一致性指纹，不冒称密码学完整数值认证；大日志另有SHA256。

来源：[Qwen3独立原日志审计](remote_review/runs/qwen3_layer02/INDEPENDENT_RAW_AUDIT.json)、[Qwen1.5独立原日志审计](remote_review/runs/qwen15_layer02/INDEPENDENT_RAW_AUDIT.json)、[本地来源与指标复核](evidence/SOURCE_AND_LOCAL_REVIEW_V5.json)。

## 4. CA页映射不再只是地址标签

新增有限物理页图像，每个模拟HB分区仍限512MiB。权重缓存按实际源内容绑定，router、KV及工作区固定；原始16位权重可动，FP32扩展临时权重工作区固定。映射仅允许分区内权重帧池双射、最多10%有效权重字节，并检查映射代际。

安装时先排空，用两个4KiB SRAM缓冲执行实际旧帧读取、循环搬移和新帧写入，完成后原子更新映射。后续读依据实际物理帧取值，不从逻辑对象副本直接返回，也不从checkpoint修复错误值。迁移DRAM流量及SRAM条带服务已推进模拟时间；CPU查询/验证/控制成本仍未认证。

真实Qwen1.5投影检查：交换8KiB的两个不同权重页后，实际primitive输出逐位不变。另验证跨权重对象交换、释放后的新工作区不覆盖仍存活权重、固定router不变；重复帧、固定对象、旧映射代际、超预算四类非法映射均被实际入口拒绝。

最终两模型单层运行也安装固定两页交换，并经独立审计确认迁移读写、后续新物理地址与KV不变。**尚未执行正式同合同完整层B/身份映射/B＋CA配对数值准入，也没有训练CA或比较收益。**

来源：[真实权重迁移及输出不变](remote_review/evidence/PHYSICAL_PERMUTATION_PROBE.json)、[四类负对照](remote_review/evidence/PHYSICAL_PERMUTATION_NEGATIVES.json)、[跨对象/PP载荷](remote_review/evidence/CROSS_OBJECT_PP_PROBE.json)、[Qwen3映射协议](remote_review/runs/qwen3_layer02/MAPPING_PROTOCOL.json)、[Qwen1.5映射协议](remote_review/runs/qwen15_layer02/MAPPING_PROTOCOL.json)。

## 5. 官方CPU层独立对照：有差异，未晋级

使用已有环境的PyTorch 2.6.0、Transformers 4.51.3官方eager decoder层，只加载同一层的实际BF16/解码FP16参数，在CPU执行相同诊断输入。没有调用GPU、构造完整模型或修改目标结果。参考模块源文件SHA及实际函数源码已保存。

| 模型/阶段 | 2048个输出中不同的存储元素 | 最大绝对差 | 所选专家集合 |
|---|---:|---:|---|
| Qwen3 prefill | 0 | 0 | 相同 |
| Qwen3 decode | 111 | 0.0009765625 | 相同 |
| Qwen1.5 prefill | 1035 | 0.00048828125 | 相同 |
| Qwen1.5 decode | 543 | 0.00048828125 | 相同 |

Qwen3 prefill的一次单token结果逐位一致，不代表cached decode、长上下文或完整模型通过。Qwen1.5仍有FP16差异；不能因误差看起来小而事后设置阈值并宣称通过。TP精度边界、数学微程序与完整原模型的数值准入仍需独立处理。

原始与修正版使用相同隐藏态输入，未根据结果换输入。本地从保存的二进制独立重算上述不同元素数与最大误差，与113回执一致。

来源：[Qwen3官方CPU对照](remote_review/runs/qwen3_layer02/independent_cpu_reference/COMPARISON.json)、[Qwen1.5官方CPU对照](remote_review/runs/qwen15_layer02/independent_cpu_reference/COMPARISON.json)、[本地复核](evidence/SOURCE_AND_LOCAL_REVIEW_V5.json)。

## 6. PP与软件检查的实际范围

新增连续层slice控制器，显式校验层区间，并将前层实际输出作为跨阶段输入。0→4→8→12三个PP4根节点边界已通过实际NoC/目的HB载荷检查；这只是PP边界服务，不是完整24层PP4模型通过。

最终113共32项软件检查通过，含实际norm配置、dtype/库身份、bias舍入、SRS/SAG、页边界、PP源数据与非法区间保护。独立数值反例、真实权重迁移、完整层及原日志审计另行计数，不把它们合成“32个模型实验”。

来源：[32项检查回执](remote_review/evidence/SOFTWARE_CHECKS_v4.json)（文件名沿用旧工具，内容为本轮32项）、[PP及跨对象检查](remote_review/evidence/CROSS_OBJECT_PP_PROBE.json)、[连续层接口](core/coupled_decoder.py)。

## 7. P0-1b为什么仍不能标完成

| 剩余项 | 当前缺口 | 下一处实现入口 |
|---|---|---|
| 原生并行调度/多请求身份 | 目前全局串行RPC，DRAM请求owner固定0，不能产生合格的跨请求时间共访画像 | `runtime/coupled_backend.cpp`、`core/coupled_backend.py`、`core/coupled_layer.py`；需并发任务推进、owner与session贯穿回调 |
| CPU/PCIe/缓存成本 | NumPy/codec/layout等软件服务执行了实际功能，但仅记录墙钟及数据流时间，未接入目标CPU服务时钟；缓存维护也未完整计费 | `software_op`及codec路径、实际CPU/PCIe/维护接口；禁止直接把主机墙钟加模拟纳秒 |
| 统一参数合同 | 当前复用的全事务Ramulator入口为256B、1.25ns；与既有32B候选及CPU/PCIe合同还未统一 | 运行合同、后端ABI与参数来源；不将本诊断参数自动升级为正式硬件选择 |
| 完整PP/多层/分页 | 仅完整层0与PP载荷边界；未验证完整PP4模型、多请求KV、跨层缓存逐出及所有生命周期 | `core/coupled_decoder.py`、缓存/allocator与目标服务 |
| 数值与配对准入 | 官方CPU对照仍有差异；固定交换不是正式CA布局，未做完整同合同B/CA配对 | 冻结精度与判据后开展最小数值门；不能按测试结果调阈值 |

因此，`p0_1b_complete=false`、`performance_ready=false`继续保留。P0-1c前轮的身份门控复用判定不撤销；新binary/精度合同又已变化，旧周期仍不晋级。

来源：[机器状态](STATUS.json)、[当前准入](contracts/gates.json)、[20项实现账本](IMPLEMENTATION_STATUS_v5.csv)。

## 8. 归档、失败与授权边界

- 上游18份所选文件与FREEZE匹配，另1份FREEZE文件本身记录现值；只读复用数学/服务源码，未修改、重启或接管世界模型/mini-SWE-agent工作线。
- 首次启动因缺少`POPNET_COUPLED`进入旧trace初始化并崩溃；有界gdb复现后补齐显式环境，原启动记录保留。这不是观察到模型数值失败。
- 一个新增概率检查最初把FP32归一化总和要求到小于一ULP，已修正为FP32精度边界；初次失败保留，未修改模型结果。
- 四个非法映射进程失败是预定负对照；不计成模型数值失败或删除记录。
- 四个单层运行上下文及各自官方CPU对照保留；没有完整语言模型前向、GPU执行或物理NPU实验。正式性能运行0。

源目录：`/mnt/sda1/h3240101068/ca_semmoe_hiband_coupled_20261102_v5`。四份约4.03GB原始大事件日志保留113，已流式独立审计并登记SHA；本地为420成员紧凑审查包，不宣称本地重算大日志或重载全部权重。旧版本源码包及结果保留，新增交付不覆盖v4。

来源：[紧凑包完整索引与远端大文件SHA](remote_review/REVIEW_MEMBER_INDEX.json)、[实际运行库身份](remote_review/evidence/RUNTIME_IDENTITY_V5.json)、[上游来源](upstream/SOURCE_CAPTURE.json)、[前轮报告](C:/Users/21747/Documents/跨层优化/ca_semmoe_hiband_native_20261102_v4/REPORT.md)、[两模型计划](D:/electronic_science/LLM芯片及系统优化/跨层优化/system_chip/261102/CA_两模型实验计划_20261102_v4.md)。

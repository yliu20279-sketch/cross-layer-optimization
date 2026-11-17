# Qwen1.5 第 5 层与高频 GetS 配对

2026-11-17 在 113 上完成两档 HiBand 参考仿真。两档均引用首次接入检查的 Qwen1.5-MoE-A2.7B-Chat-GPTQ-Int4 第 5 层 prefill 单 token，沿用 Top‑4、15 笔 MoE 传输、输入及输出指纹和原串行服务间隔。GetS 为 32 B 请求、64 B Bank 读及 64 B 回复。回复由 Bank 完成事件放行。冻结文件 `combined_overload.json`、`matched.json` 包含每笔到达、地址、端点和字节，可逐笔复用。

GetS 连续释放 512 周期。去程和首个 MoE dispatch 共用 NI0→NI1。首个 dispatch 在周期 32 就绪，4,096 B 对应 128 个 32 B flit。以 1 flit/周期名义发送能力定义 `[32,160)` 的需求窗口。MoE 标称需求为 1 flit/周期。GetS 回复沿反向路径，未纳入该出口的去程需求。

| HiBand 档位 | GetS 笔数 | GetS / 合计需求（flit/周期） | 固定窗口内 GetS 就绪 / 注入 | 最后一笔回复完成（周期） | 最慢 GetS（周期） | MoE 片段与汇合完成（周期） |
|---|---:|---:|---:|---:|---:|---:|
| 合计超载，每两周期一笔 | 256 | 0.5 / 1.5 | 64 / 0 | 1,570 | 1,062 | 208,211,880 |
| GetS 与 MoE 需求相当，每周期一笔 | 512 | 1.0 / 2.0 | 128 / 1 | 2,650 | 2,140 | 208,213,243 |

572 和 1,084 个 PopNet 包分别全部收齐。两档都选择 `FULL_LOCAL`。HiBand 参考模型承载在 PopNet Mesh 上，源/目的 NI 按网络操作预留序列化时段，首个 4 KiB dispatch 占用源 NI 后，多数已就绪 GetS 在窗口之外才注入。表中的需求为外部 offered load，实际注入来自 `packet_completions.csv` 的后端入队记录。此回放可以确认入口积压，且不能从这两条记录直接量出物理链路的仲裁争用。MoE 时延使用冻结的计算和内存间隔，范围到该层 MoE 后缀完成。

原始目录由 `remote_run_path.txt` 记录。两档目录各含输入副本、启动参数、完整事件、Bank 回调、包记录和事务审计。`LAUNCH.json` 绑定使用的输入、脚本和可执行文件指纹。

## 113 上的第二臂接入检查

从提交 `bcbee2c4` 下载并校验的 63 个 Thermal 文件已复制到远端 `joint/thermal_bcbee2c4`。发布系数文件的传输未完成，使用该提交的原始 RC 矩阵和官方重建脚本在 113 生成了独立系数文件，1292 状态模型的 256 步参考回放最大误差为 2.22×10⁻¹⁴°C。重建件有独立 SHA-256。 [Thermal 准备回执](THERMAL_PREPARATION.json) · [Thermal 源码](https://github.com/yliu20279-sketch/cross-layer-optimization/tree/bcbee2c4/thermal)

复用同一冻结到达文件，在 Verilator 中以首个 128 flit MoE dispatch 与 GetS 做入网检查。测试台使用项目现有的逻辑 Bank 服务，GetS 数据回复长为两个 32 B flit，回复读取受请求完成约束。两档分别完成固定 Mesh、仅旁路 MoE、仅旁路 GetS、同时旁路四种候选。切换臂在周期 32 决策，周期 72 安装就绪，安装前没有选入的帧走旁路。仅旁路 MoE 使两档 GetS 尾部提前 16 个 RTL 周期，同时两档首个 dispatch 的目的 Bank 完成都晚 39 周期。仅旁路 GetS 各提前 1 周期，未超过 1 周期误差余量。同时旁路使两档汇合均变慢。因此两档均保留 Mesh。适用范围为首个 dispatch 的 RTL/逻辑 Bank 回放。 [候选与审计](RTL_INGRESS.json)

已把现有 15 个传输之间的串行服务拆成实际 RPC 及其余服务，并将 25 笔矩阵 RPC 逐一绑定原后端 lowering（含计算与 Bank 周期）。Thermal 分支有 24 笔同形状算子的候选 OPP Profile，缺少 `M=1,K=2048,N=1` 的共享专家 gate。前两种形状在旧 Thermal 满频 Profile 中的示例时延约 1.09 和 1.19 ms，原生矩阵 RPC 约 5.43 ms。现有 Profile 针对 32 GiB 平台及其访存布局，HiBand 参考合同使用 8 GiB 平台，原生 RPC 又包含自己的 DMA/Bank 边界。 [矩阵与服务边界](NATIVE_TIMED_SERVICES.json)

## 原生后端 OPP 标定

在原来的 8 GiB 后端独立构建 OPP 接口，按每次矩阵 RPC 锁存计算及其 SRAM 的相对频率，按实际放行时间启动，DRAM/HB/NoC 时钟依旧按原配置推进。1.0、0.75、0.5 三档均跑完同一第 5 层，三档的 25 笔矩阵及层输出与原记录逐位一致。1.0× 的 25 笔矩阵起止时刻也与冻结记录逐项相同。层完成时间分别为 259.378504、289.304335、348.385624 ms。独立小矩阵在注入 1 ms 放行等待后，后端实际开始推迟 1 ms，证明放行门可作用于目标时钟。 [三档回执](native_opp_results/) · [放行探针](native_opp_results/OPP_ACTUATOR.json)

## 原生 NoC＋Thermal 单层混跑

两档在 113 上完成。同一第 5 层、同一组冻结 GetS 请求在一个原生时钟中运行。每笔请求经共享 PopNet 后，在目标 Ramulator2 分区提交两个 32 B 读，全部回调后才发两个 32 B flit 的回复。后端按前述 RTL 候选筛选结果保留 Mesh。Thermal 控制器使用三档实测模拟时序，逐笔给出 OPP 和放行时间，由后端等待并执行。两档均有 24 笔矩阵使用 0.75×，共享专家 gate 使用 0.5×。25 笔实际开始时刻逐一匹配控制器命令，45°C 初态下额外热延期为 0，降频改变算子完成时间和后继就绪时刻。两档输出与冻结结果逐位一致。

| GetS 笔数 | HiBand 最后一笔回复（ns） | NoC＋Thermal 最后一笔回复（ns） | HiBand 汇合（ms） | NoC＋Thermal 汇合（ms） |
|---:|---:|---:|---:|---:|
| 256 | 1,570 | 1,632 | 208.211880 | 238.181671 |
| 512 | 2,650 | 3,276 | 208.213243 | 238.181672 |

计时均从 GetS 外部到达序列起点开始，汇合取本层 MoE 结果与所有 GetS 回复的较晚者。两套执行器的 NoC/NI 服务与端点访存实现不同，表中数值仅作逐档诊断。第二臂的热判断沿用发布版 32 GiB RC 和活动换算系数，时序来自当前 8 GiB 原生后端。保留 Mesh 的决策源为首个 dispatch 的 RTL 候选筛选，混跑验证覆盖该决策的执行及闭环调频。 [逐档审计](native_opp_results/COMPARISON.json)

## NoC-only 单层混跑

在 113 关闭 Thermal 并固定 1.0×，重新运行首个 dispatch 的 NoC 候选筛选。两档均选择保留 Mesh，原生后端在该配置下跑完整个第 5 层。两档逐笔验证冻结 GetS 的到达、共享 PopNet 和目标 Bank 的完成顺序，25 笔矩阵及层输出通过冻结指纹校验。

| GetS 笔数 | 最后一笔回复（ns） | MoE 与 GetS 汇合（ms） | 第 5 层全层（ms） |
|---:|---:|---:|---:|
| 256 | 1,632 | 208.245056 | 259.374894 |
| 512 | 3,276 | 208.248966 | 259.378804 |

最后一笔回复与汇合从 GetS 到达序列起点计，全层耗时从第 5 层输入开始计。两份 `GETS.csv` 与前一轮同档原生热臂逐字节相同。该比较复用前一轮回执。 [验收汇总](noc_only_results/SUMMARY.json) · [候选筛选](noc_only_results/RTL_INGRESS.json)

## 同原生后端的 HiBand／本文 NoC 配对

四臂在 113 的独立目录运行同一原生 PopNet＋Ramulator2 二进制，固定 1.0× 并关闭 Thermal。两臂共用原生 NI、端点和队列实现，每笔 GetS 发出 32 B 请求，目标 Bank 完成两次 32 B 读回调后才发出 64 B 回复。使用相同的第 5 层单 token prefill 输入、真实权重和 256／512 笔冻结 GetS 到达序列。

HiBand 臂接入项目既有的四种带宽分配模式，承载仍使用共同的 Mesh；这里不模拟 HiBand 论文的 split-Benes 物理互连。本文 NoC 臂执行首个 dispatch 的 RTL 候选筛选结果，两档均保留 Mesh。该用例所有网络流量都在同一分区内，HiBand 因此选择 `FULL_LOCAL`，两臂对此流量均有每周期 1,536 B 的逻辑准入预算；实际包和 flit 仍受同一原生 NI 和 PopNet 路由器约束。

| GetS 笔数 | 最后一笔回包：HiBand／本文 NoC（ns） | 单笔最大时延：HiBand／本文 NoC（ns） | 汇合：HiBand／本文 NoC（ms） |
|---:|---:|---:|---:|
| 256 | 1,632／1,632 | 1,122／1,122 | 208.245060／208.245060 |
| 512 | 3,276／3,276 | 2,765／2,765 | 208.248963／208.248963 |

最后一笔回包和汇合从首笔 GetS 外部到达计；单笔时延从该笔外部到达到完整回包计。两档同组的逐笔 GetS、NoC 传输和 25 笔矩阵时序均逐字节相同，层输出指纹与冻结参考一致。每臂记录 54 次逻辑预算暂缓；共同准入预算与上一节 NoC-only 单跑的实现有差异，上一节的毫秒数不代入本表。两档均由 MoE 完成决定汇合。旧表的 62／626 ns GetS 尾差在本次配对中消失；由于此处同时统一了回调、NI 和端点服务，旧差值不能单独归因于读回调粒度。结果适用于这层的本地流量与所选策略，不覆盖跨分区或激活旁路的情况。

[验收汇总](paired_native_results/SUMMARY.json) · [四臂输入指纹](paired_native_results/INPUTS.sha256) · [本地审计脚本](audit_paired_native.py)

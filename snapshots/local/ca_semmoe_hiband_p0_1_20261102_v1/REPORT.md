# P0-1：CA、Sem-MoE 与 HiBand 合同及源码审计

日期：2026-11-02（Asia/Shanghai）。状态：**审计完成，组合基线未就绪**。本轮仅本地读取、哈希和隔离文档/源码快照；未 SSH、未导入实验模块、未运行采集、构建或性能实验，不修改旧结果。

## 1. 判定

固定模型为 Qwen3-30B-A3B 与 Qwen1.5-MoE-A2.7B。P0-1 已完成本地可取得证据的审计与身份冻结；这不等于性能准入。不能把当前组合标为作者完整系统或 SOTA 等价实现。下一阶段不能直接将旧组合用于在线服务性能主张。

已冻结的是具体历史 CA4 参考、源码及配置快照，而不是凭空补齐尚未实现的完整方案。真实时间共访 CA 与结构代理 CA 分开；最终真实时间 CA 仍待定义，不默认为本轮参考版本。

## 2. CA 版本区分与冻结参考

| 版本 | 粒度与共访定义 | 可用范围 |
|---|---|---|
| Qwen3 soft70 旧版 | 每专家约 2.25 MiB 逻辑单元；不同请求权重读取区间交叠 | 迁移筛查与历史失败，不与 4KiB 结果合并 |
| Qwen1.5 memory-stress 旧版 | 每专家抽取 16 个 4KiB 页；同层同波次跨请求共现 | 压力正例，不等于真实服务时间重叠 |
| 本轮冻结参考 CA4_STRUCTURAL_STAGE2_REFERENCE_20261102 | 4KiB；历史 N_DEV DAG 同深度不同张量的同页偏移配对 | 两模型统一的可审计结构代理，历史开发参考 |
| 最终真实时间 CA | 尚未冻结事件边界、时间窗口及在线可见性 | 不能宣称实现完成 |

参考实现来自 `page_management_stage2_natural_v2/experiment.py` 的 model_data、score、optimize、materialize。可动对象是 partition 内 FP16_weight 且排除 router；非权重地址固定。目标按 (同 Bank 共访代价, Bank 热度平方和) 字典序下降，不是未经定义的加权和。种子、2万次/60秒先到、10%起点改动预算见 CONTRACT.json。搜索存在墙钟截止，不能仅凭 seed 承诺跨机器逐字节复现。

历史起点 Qwen3 为 PHASE4，Qwen1.5 为 XOR4；它们是旧 DEV 选定起点，不冒充新 TEST 选择。4KiB Bank 解码为 ((frame>>2)&3)*4+((frame>>4)&3)。16/64KiB 投影另算，不纳入 CA4 身份。随机生成器是条件洗牌和修复，不是全空间均匀采样。

来源：[结构代理实现](sources/page_management_stage2_natural_v2/experiment.py)、[旧协议](sources/page_management_stage2_natural_v2/EXECUTION_PROTOCOL.json)、[冻结起点](sources/page_management_stage2_natural_v2/DSTAR_FREEZE.json)、[历史两版 CA](sources/COACCESS_BANK_LAYOUT_QWEN3_QWEN15_REPORT.md)。

## 3. 两模型组合基线覆盖矩阵

| 对象 | Qwen3-30B-A3B | Qwen1.5-MoE-A2.7B |
|---|---|---|
| 模型身份 | 历史 experiment_definition 记 revision 8143878278a202cc0ff9ef1bbe00b2abb1adf86d；不是本轮验证权重 | model_config 提供模型 ID 和 main/config.json，未给不可变 checkpoint/tokenizer revision |
| 旧并行配置 | Sem-MoE 脚本 48 层、128 专家、EP16、每 rank 8 专家 | 24 层、60 专家、Top4、PP4×TP4/EP4、每 rank 15 专家 |
| 专家放置 | profile 请求亲和交替分配与专家交换；非作者代码等价 | token/expert 交替聚类启发式；非完整作者求解与运行栈 |
| 在线调度 | evaluate 和 baseline 读取评价请求实际 expert 计数，逐层重新分配请求；不具无未来信息在线语义；2-gram 未实现 | evaluate 的 request_to_rank 来自评价实际 expert 计数；主指标使用 token_to_rank，不能直接当在线 DP 调度实测 |
| 数据分离 | 原记录有20/80请求分离；这不消除评价阶段实际路由可见性问题 | main 在 profile/eval 任一为空时两者回退 rows；有重叠风险，限制文本仍可能声称 disjoint |
| 通信 | 旧图与回放代理、teacher-forced 路由；非完整生成服务 | 每 rank 一个 peer 聚合远端字节，非真实 all-to-all 目的地；命名 SRS/SAG 节点不能证明融合算子实现 |
| 计算与权重 | 多阶段代理和新 BF16 连续两层合同并存，不能拼接 | lower_legosim 明写解析周期、48MiB代表权重服务、至多2048B采样，不回放checkpoint分配地址 |
| HiBand | coupled_main 有模式预算、BSA/BGA share、HIC serial 控制等研究模型；不等于完整作者 HIC/SOR/split-Benes | run_server_smoke 给所有方案 HB_FIXED_MODE=GLOBAL_BIAS，不能据此认定 HiBand 动态模式收益 |
| 架构 | V3.6 execution overlay；历史W4/host8和新BF16/host128必须分账 | canonical 与 overlay 的channel_width/事务字段不一致；overlay 不冒充canonical执行 |
| 本轮准入 | NOT_READY_FOR_FORMAL_COMPOSITE_PERFORMANCE | NOT_READY_FOR_FORMAL_COMPOSITE_PERFORMANCE |

代码结论限所审查入口，不推断全项目绝无其他实现。现有摘要/验证中的 PASS 不消除上述语义边界。旧20/80独立性验收保持原范围，不改判为当时放置训练数据泄漏；新增发现针对在线调度可见性。

来源：[Q3 placement](sources/qwen3_30b_a3b_v3_6_experiment/sem_moe_placement.py)、[Q3模型与协议](sources/qwen3_30b_a3b_v3_6_experiment/experiment_definition.json)、[Q3既有验证](sources/qwen3_30b_a3b_v3_6_experiment/sem_moe_ctx128_validation.json)、[Q15调度](sources/qwen1_5_moe_a2_7b_v3_6/sem_moe.py)、[Q15 lowering](sources/qwen1_5_moe_a2_7b_v3_6/lower_legosim.py)、[Q15 launcher](sources/qwen1_5_moe_a2_7b_v3_6/run_server_smoke.py)、[Q15配置](sources/qwen1_5_moe_a2_7b_v3_6/model_config.json)、[Q3后端](sources/qwen3_30b_a3b_v3_6_experiment/coupled_main.cc)。

## 4. HiBand 参数与成本边界

V3.6 README 记16 partition、每个512MiB、总8GiB、25.6GB/s每对；配置就绪不是整体执行通过。Q15 README明确 canonical channel_width=16、32B事务与旧耦合ABI冲突，overlay恢复128及已验证ABI字段、保留16384行。本轮快照同时保存canonical与overlay，未替用户选择或改写它们。

Q3历史协议的PCIe5 x16有效55.04GB/s/方向及250ns单程是模型假设，不是测量。coupled_main 的 CPU 节点即时完成，DMA是方向带宽/固定延迟及共享信用抽象；这些不能代替完整host软件成本。HiBand官方artifact、厂商DRAM与论文数值对齐缺口仍保留。

需要补全的成本包括：页查询/cache、画像采集与构造、安装复制、版本切换、缓存维护、CPU软件、分页控制、完整算子/SRAM及硬件实现成本。静态账本不等于净收益。

来源：[架构说明](sources/whisper_operator_inventory/target_architecture_v3_6/README.md)、[Q15 overlay说明](sources/qwen1_5_moe_a2_7b_v3_6/README.md)、[HiBand状态](sources/hiband_reproduction/STATUS.md)、[旧运行栈身份](sources/page_management_stage2_natural_v2/RUNTIME_SNAPSHOT.json)。

## 5. 本次补发现的可复用空间诊断

此前计划将P1-1列为待补，但本次定位到Q3已有7组 strict owner-shadow 配对摘要。固定默认容量ctx128 c2/c4/c8的敏感性比例分别约0.000694%、0.002619%、0.001885%；探索高偏斜ctx128 c8约0.069908%、ctx512 c8约0.028101%。容量1024MiB对照是负差。它们显示该历史代理配置中暴露差分小，但不是新CA的普遍上界，不应直接当已认证完整系统Bank成本。

这项证据可用于P1-1设计和避免重复；只有二进制、配置、DAG、初态和干预语义匹配时才复用旧周期。本轮仅核对CSV算术及provenance快照，未重验七组原始事件。

来源：[7组摘要](sources/qwen3_30b_a3b_v3_6_experiment/figure_evidence/strict_bank_v2/phenomenon_summary.csv)、[来源索引](sources/qwen3_30b_a3b_v3_6_experiment/figure_evidence/strict_bank_v2/provenance.json)、[历史说明](sources/qwen3_30b_a3b_v3_6_experiment/PROGRESS.md)。

## 6. 不得拼接的合同与可复用范围

旧CA4是目标FP16、固定完整MoE块回放；旧组合另有理想INT4存储/解析计算；新swe_qwen3是原BF16、host128/HB8、GPU差异保留的连续两层。新数值/缓存/持有权证据不能自动补齐旧组合的在线调度和性能语义，Q15也不能继承Q3执行验收。

历史已见DEV/TEST保持已见，不恢复留出身份。旧原生二进制/库哈希在RUNTIME_SNAPSHOT为历史回执，本轮没有解包执行或重新认证远端动态链接。

来源：[旧CA4结果](sources/page_management_stage2_natural_v2/REPORT.md)、[新Q3两层](sources/swe_qwen3_continuous_lowering_20261031_v3/REPORT.md)、[持有权范围](sources/swe_qwen3_lifetime_owned_20261102_v8/REPORT.md)。

## 7. 下一步缺项与验收处置

| 缺项 | 处置 |
|---|---|
| 最终CA是否真实时间共访 | 先定义事件边界、历史可见性、求边与更新规则，另建版本；不得冒用结构代理结果 |
| 两模型在线Sem-MoE | 将实际评价路由仅用于执行/诊断；决策只读取可用历史/当前输入；补DP/TP适用范围与缺失算子 |
| Q15分组回退 | 后续实现中缺分组应拒绝性能准入，而非静默重用数据；本轮不修改历史代码 |
| Q15 HiBand固定模式 | 后续明确动态与固定基线及切换成本，不将三种同固定模式smoke当动态收益 |
| 模型/精度/资源合同 | 绑定不可变checkpoint、tokenizer、精度、容量与运行路径；Q3旧revision不默认为新BF16合同revision |
| 真实执行身份 | 冻结所选二进制/动态库/配置/输入，不从目录名PASS推断 |
| 成本及计时 | 留待P0-2及后续成本阶段，缺失时保留限定范围 |

本轮结论是P0-1审计与参考快照完成，完整组合性能基线准入未通过。不启动P0-2、P1、采集、构建或后台任务。

## 8. 交付与核验

CONTRACT.json保存机器合同与历史CODE_FREEZE逐项比较；SOURCE_MANIFEST.json保存所审查文件的字节数、SHA256、原路径与隔离副本。副本逐项重算哈希一致。快照不包含大型日志、模型权重、全部运行二进制，不是可独立重放的完整artifact。

参考论文：[ICLR官方Sem-MoE论文](https://proceedings.iclr.cc/paper_files/paper/2026/file/f0552f14388d95b19740dee809f5cad1-Paper-Conference.pdf)。论文身份与第3节语义沿上一轮全文阅读，本轮未重新联网或宣称全量文献检索。

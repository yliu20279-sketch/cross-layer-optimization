# Cross-Layer Optimization

跨层优化方法与benchmark基线研究仓库。首批内容为CA与四个MoE benchmark基线，后续可加入其他优化方法。

## CA–NoC 接口集成（2026-11-08）

[独立集成入口](integration/ca_noc_20261108/README.md)：已实际运行物理页交换、目标 NoC 完成反馈与 NPU 数值消费者短链。此版本为串行有界联调，不是完整应用或全方法性能基线；保留原 CA/NoC 快照，未覆盖其历史验收状态。

## NoC 增量归档（2026-11-08）

[NoC 源码、RTL、复核入口与验收说明](noc/20261108/README.md)：22 项控制协议、216+774 项连接、4 项配置/接收就绪组合、真实 Qwen 首块 CS/两块 Mesh 与原生动态短链的限定正确性验收。包含项目适配源码、旧内核补丁和来源哈希，不含完整第三方仿真器、权重、Trace、大日志或运行二进制。此归档不改变下方 11 月 6 日 CA/benchmark 快照的原验收状态，也不代表完整 HiBand 或优化性能实验完成。

2026-11-06采集，私有研究仓库。收录CA代码及Qwen3-30B-A3B、Qwen1.5-MoE-A2.7B、mini-SWE-agent和LingBot TI2V的基线建立代码、配置、局部验收与历史诊断。原始目录名和源码保持不变，按本地与113来源分开。目录名中的日期不等于完成日期，局部PASS不代表完整系统性能验收。

## 入口与当前边界

| 工作线 | 优先入口（snapshots/remote下） | 验收定位 |
|---|---|---|
| CA | ca_p0_1b_native_20261103_v11、ca_p0_1b_dual_migration_20261103_v10、ca_semmoe_hiband_coupled_20261102_v5 | 双请求局部数值、迁移、KV发射和权限拒绝；完整成本、并行与正式准入仍PARTIAL |
| Qwen3-30B-A3B | qwen3_30b_a3b_v3_6_experiment、swe_v7_ackfix_independent_review_20261105_v1、swe_qwen3_continuous_portable_20261103_v7_ackfix | 两层数值、ISA、写回和时钟有限验收，不等于系统基线B冻结 |
| Qwen1.5-MoE-A2.7B | qwen15_step4_tx32_W0VFwG；本地qwen15_p0_1b_baseline_plan_20261103_fffa1cc0和qwen15_step2_binding_bb1e8669 | FP16/K64合同、TP/EP/PP与32B事务准入；既有prefill差异与四stage诊断须按最终回执解释 |
| mini-SWE-agent | swe_qwen3_lifetime_owned_20261105_v8_phasefix；本地swe_bmk_baseline_20261103 | KV持有权修订与两轮验收链；10:35快照第二轮仍运行。模型局部通过不等于官方任务resolved |
| LingBot TI2V | lingbot_step5_continuous_20261102_v11、lingbot_v11_baseline_freeze_20261103、lingbot_step3_closeout_20261105_v3、lingbot_step4_target_chain_20261105_v1、lingbot_cpu_vae_repair_20261105_v1 | 连续单层两轮及单K投影成本门有限通过；CPU VAE差异修复、完整视频时序及全成本仍待验收 |

本表是采集前已核对状态，新增源码或运行中间产物不自动提升验收。`snapshots/*/SOURCE_COLLECTION.json`记录采集文件、来源路径、SHA及被大小限制排除的文件。`SOURCE_MANIFEST.json`核对实际归档字节。相同目录的本地和113版本可能不同，后者也可能是运行中的非原子快照；切勿无条件覆盖合并。

## 使用与依赖

先读对应目录README、REPORT、PROTOCOL、FREEZE及运行脚本，再选择明确范围的入口。本仓库不自动运行实验，审计/准备脚本也可能构建、上传或启动进程。许多脚本保留113绝对路径及同级历史目录依赖，需在隔离工作区按源合同配置。

依赖包括Linux、C/C++工具链、Python及各实验冻结环境、PyTorch/NumPy、Sniper、InterChiplet、NPUSim、Ramulator2、PopNet；具体版本和构建命令以源目录冻结记录为准。规范V3.6小型配置在architecture/v3_6，执行overlay必须单列。当前代码快照不包含完整工具链安装。

未上传模型权重、张量fixture、完整路由/Trace、原始CPU大日志、二进制、虚拟环境、压缩交付包和凭据；缺少这些外部资产时不能宣称可直接全量复现。外部依赖与输入仍按源报告及原清单哈希取得。历史报告的相对链接可能指向未收录数据，原始绝对路径仅作来源定位。

完整系统B尚未冻结，正式性能矩阵及策略净收益未建立。正式实验等待全套优化合入并准入，再做B对B＋全套优化和关闭CA消融。历史受控收益、代理结果、原生事件验收与物理硬件性能分别保留范围。

## 来源与权利

本仓库为研究代码备份，不新增开源许可；原作者版权、上游许可证和使用条件继续适用。模型与第三方工具不在本次授权下重新许可。上传前检查见UPLOAD_CHECK.json；第三方源码保留原文件头。

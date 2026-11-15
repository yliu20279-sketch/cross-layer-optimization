# MoE thermal-aware execution

本目录收录 **Qwen1.5-MoE-A2.7B** 的热管理代码、必要数值输入、对照实验和审计工具。它是独立的架构级诊断模块，不包含其他工作线的可重构 NoC 实现，也不把早期 dense Qwen3-8B 或 π0.5 的结果计作 MoE 结果。

## 工作负载与边界

- 24 层、60 个路由专家、Top-4；每请求 512-token prefill 和 1-token decode，正式实验每批 4 请求。
- 专家选择和 token 路由为**建模输入**，不是运行 checkpoint 得到的真实 Gate/logit 轨迹。本目录不包含模型权重、提示词数据集或数值推理验收。
- 固定 4×4 Mesh、16 个计算簇、32 GiB DRAM，使用已校准的 NPUSim 计算计划和 Ramulator2→DRAMPower 访存 Profile。
- 本次热诊断使用 2 GHz 标称计算频率、Rconv=3 K/W、45°C 环境、60°C 软目标、65°C 策略上限和 64°C 预测守卫。65°C 是诊断策略上限；原生 RR1 Profile 的适用温区仍须低于 85°C 刷新阈值。
- 使用完整 1292 状态、96 输出块的 RC 模型，1 ms 热步长。访存仍是有界的逐任务 Profile，不声称维护全应用连续 DRAM 命令/row-buffer 队列。
- 每次任务派发统一计 10µs 模型开销。宿主 Python 运行时间不计作硬件性能收益，控制器硅片开销未校准。

## 目录

| 路径 | 内容 |
|---|---|
| `src/moe60_controller.py` | 相同 OPP 表下的 AMBER 风格预测调度、热响应上界准入，以及无准入消融 |
| `src/amber_online_qwen.py` | AMBER 两阶段机制的目标平台适配；不是作者官方完整复现 |
| `src/moe60_runtime.py` | 专家执行位置、工作区生命周期、真实付费复制，以及通信/温度记账 |
| `src/graph_scheduler.py` | 完整任务 DAG、计算簇、存储分区和固定 XY 链路的因果调度 |
| `runtime/` | 上述实现依赖的原有 native 执行类、固定 Mesh 预约和功耗渲染 |
| `inputs/` | 冻结任务图、合成路由描述、物理布局、Profile、OPP 表、RC 系数及共同暖态 |
| `reference_results/` | 原正式实验的紧凑结果、协议、审计和首批任务/通信文件指纹 |
| `validation/` | 对重跑产生的完整记录做独立审计；原始完整记录不随仓库上传 |
| `tools/` | 可移植性检查、OPP 表重建、逐算子 Profile 重放和 RC 核生成 |
| `provenance/` | 原始来源、移植变更和本次上传验证记录 |

`inputs/routing.json` 和 `semantic_flows.json` 是无执行时间戳的建模任务/消息描述，不是完整运行 Trace。RC 模态系数和暖态以 JSON 保存；运行时自动生成的 NPZ 缓存位于 `.cache/`，不提交 Git。

## 环境与快速验证

从本目录执行。推荐 Python 3.11；本次验证使用的版本见 `requirements-tested.txt`。

```bash
python -m pip install -r requirements-tested.txt
python src/run_moe60_mechanisms.py --case prepare
python src/run_moe60_mechanisms.py --case self-test
python tools/rebuild_opp_table.py
python tools/check_portable.py --case contract_energy
python tools/check_portable.py --case amber_energy
```

最后两个检查各实际执行一批 60,824 个任务：核对时延、能耗、峰温和 D60，并要求完整 `tasks.csv` 与 `flows.csv` 的 SHA256 等于原冻结结果，再做逐 bin 功耗重建和全阶 RC 重放。它们不只是重绘既有结果。精确文件指纹检查以冻结环境为准；不同数值库/平台产生差异时应保留差异。

所有新输出写入忽略的 `runs/`，可用 `THERMAL_RUN_DIR=/absolute/path` 改到其他隔离目录。已完成结果带有源码哈希，不能静默覆盖；修改代码后应使用新的输出目录。首次准备完成前不要让多个进程共享同一输出目录。

## 对照与消融

先运行一次 `prepare`，再选择需要的 case：

```bash
python src/run_moe60_mechanisms.py --case amber --requests 4
python src/run_moe60_mechanisms.py --case amber_energy --requests 4
python src/run_moe60_mechanisms.py --case energy_none --requests 4
python src/run_moe60_mechanisms.py --case contract_full --requests 4
python src/run_moe60_mechanisms.py --case contract_energy --requests 4
```

| Case | 选频 | 热控制 |
|---|---|---|
| `amber` | AMBER 风格最高安全 OPP | 有限预测窗口与两阶段调度 |
| `amber_energy` | 固定局部能耗最小 OPP 表 | 相同 AMBER 风格预测调度 |
| `energy_none` | 同一能耗 OPP 表 | 无热准入，不能据单轮安全推断持续安全 |
| `contract_full` | 固定全速 | 完整 RC 未来响应上界准入 |
| `contract_energy` | 同一能耗 OPP 表 | 完整 RC 未来响应上界准入 |

选频的比较键是算子 Profile，而不仅是 `op` 名称；它还包含工作量和访存地址布局等配置。选择规则为局部动态能量加执行域空闲功率乘服务时间，平局时优先较短时延、再优先较高频率。

当前 MoE 契约调度从有界就绪集中选择最早资源可行且热安全的任务，计算/访存需求互补只用于平局。没有按 DAG 剩余关键路径排序。契约模式对 NoC 事件也单独做准入；AMBER 对照没有这一独立通信准入门。

探索性专家动作也保留：`replica_control`、`replica_select`、`dynamic`、`dynamic_forced`、`dynamic_forced_control`。复制的读取、XY 传输、写入、资源占用、能耗和发布时序均计费。只有动态策略确实复制时，`dynamic_copy_control` 才适用。本次动态策略复制次数为零，不能把其微小调度差异称为迁移收益。

完整单轮集合重跑后可执行：

```bash
python validation/audit_and_report.py --final
```

## 连续运行比较

```bash
python src/run_moe65_fixed12.py --plan
python src/run_moe65_fixed12.py --policy amber_energy
python src/run_moe65_fixed12.py --policy contract_energy
python validation/audit_fixed12.py
python validation/plot_results.py
```

两种策略各连续执行 12 批，不在批次间重置完整热状态；固定第 7–12 批计量。用第 7–9 批和第 10–12 批检查温度均值、批时延和最慢模态漂移。探索性的严格逐批周期判据及中断试跑没有混入正式窗口。

原正式结果：

| 指标 | 同选频 AMBER | 能耗选频＋契约准入 |
|---|---:|---:|
| 后 6 批平均批时延 | 12.948333 s | 13.258333 s |
| 持续吞吐 | 0.308920 req/s | 0.301697 req/s |
| 全程峰温 | 64.000562°C | 63.976314°C |

两者都满足 65°C 诊断上限；契约准入时延高 2.394%，不是吞吐优势。原 AMBER 与能耗选频的单轮对比、迁移负结果也保留在参考报告中。它们不构成 NoC 重构的评估结果，也不替代仓库其余 benchmark 的完整系统验收。

## 重建离线数值输入

```bash
# 重放提供的 native 计划；默认仅一个唯一配置，属于诊断。
python tools/reprofile_operators.py --limit 1
# --limit 0 可重放全部唯一配置，不重建外部模拟器。
# 根据物理 RC 矩阵独立重建热响应核，输出与冻结输入分开。
python tools/compile_thermal_kernel.py
```

这些命令不调用外部权重/数据集，也不重建 NPUSim、Ramulator2 或 HotSpot。本次上传包含其原有校准输出；重新校准底层模拟器仍需原工具链及相应源合同。不得把 Profile 重放或局部 PASS 表述为 checkpoint 数值推理或硅片性能验收。

## 来源与结果文件

- [单轮对比](reference_results/mechanisms/RESULTS.md)
- [连续运行正式对比](reference_results/sustained65/RESULTS.md)
- [移植说明](provenance/PORTING.md)
- [来源清单](provenance/SOURCE_MANIFEST.json)

原始本地实验未修改。参考 JSON 保留历史路径和哈希作为来源信息；它们不是移植后程序的运行路径。新的运行使用相对包路径和独立输入清单。完整任务/通信/温度 Trace、大日志、虚拟环境和二进制不提交仓库，可通过上述脚本在本地产生。第三方与原作者的许可和使用条件继续适用，本目录不新增开源许可。

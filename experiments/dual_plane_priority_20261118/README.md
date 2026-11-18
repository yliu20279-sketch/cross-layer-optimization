# L1/L2：类型优先级 RTL 实验与120组结果

截至北京时间2026-11-18 15:51采集：120/120组仿真PASS，包含预检24组复用及新增96组，共720个通信阶段。仿真于14:45:02完成；本地独立审计5339项检查通过。上传只整理与校验既有文件，未重新运行仿真、综合或物理实现。

## 来源和分工

用户确认lyc指本人，本包覆盖原计划L1连线/HiBand适配核查和L2类型优先仲裁。C1—C4仍归计划作者；L3同版本四臂硬件代价没有在本包验收。原计划见[USER_PLAN.md](USER_PLAN.md)，历史执行细节及失败边界见[HISTORICAL_EXECUTION.md](HISTORICAL_EXECUTION.md)。

发布基于上游312组结果提交[6bd70c2a](https://github.com/yliu20279-sketch/cross-layer-optimization/commit/6bd70c2a46c009243ec4f158f14f22429d6ac71f)，本轮实际测试源码基准为090a55d0；二者由[UPSTREAM.json](UPSTREAM.json)分开记录。新源码见[package/](package/)，冻结digest为ba05961d5de61bdf，原始差异见[SOURCE_CHANGE.patch](SOURCE_CHANGE.patch)。本地76dbaa8d为独立源码审查仓库中的历史提交号，本发布不以它作为上游祖先。

loveYoumu已经运行、已有结果、等待或排队的实验均未重跑；原312组与pilot只作只读参照。本批24组预检通过后只补96组，未重新构建或重跑24组。

## 实验清单和方法

| 项目 | 方法与结果 |
|---|---|
| L1连线和适配 | 36条NI到下层CS附着、8条CS间双向连接、8个上层闲置端口；120种5有效端口Beneš排列静态检查通过。CS宽接收输入改为只接物理相邻端口。见[L1静态审计](L1_STATIC_AUDIT.json)及[论文映射](L1_PAPER_IMPLEMENTATION_MAPPING.csv)。 |
| L2实现 | TYPE_PRIORITY默认0保留RR；=1时CONFIG/ACK→DataS→GetS→MoE。修改NI发送/接收和路由器仲裁，同类RR、包锁定、队列、链路及SRAM预算保持原口径。 |
| 新版本功能门 | C++定向探针及共享Mesh、HiBand四模式、双平面和控制器共同回归通过；真实[BUILD.json](receipts/1547eea9172ebef6/BUILD.json)记录命令与二进制哈希。 |
| 24组预检 | 16 token seed641103，热点/分散×间隔1/3/6，共6例×4臂；144阶段。 |
| 全120组 | 冻结30例（4/8 token各1输入、16 token三seed；两种摆放、三种间隔）×共享Mesh/HiBand FG/GB/LB四优先臂。Bank latency=8，clock_ns=1。8 worker，每组1CPU/3GiB/900秒；不重复执行已有结果。 |

完整逐组清单：[FULL_EXPERIMENT_CHECKLIST.csv](FULL_EXPERIMENT_CHECKLIST.csv)。30份冻结输入在[cases/](cases/)，120份原始JSON在[results/](results/)，120份旧RR配对结果在[rr_reference/](rr_reference/)。快照记录源/二进制哈希，未上传运行二进制。HiBand为256-bit平台适配，原文Fig.6、§4—5：[DOI](https://doi.org/10.1145/3770743.3803944)；不附论文全文或页面图。

## 结果及适用范围

下表是各例“RR指标÷优先级指标”的几何均值，大于1表示该指标缩短。汇合是六个独立通信阶段的完成周期之和；P99列为每例最大阶段GetS P99之比再取几何均值。

| 臂 | 汇合比值 | MoE比值 | GetS P99比值 | 汇合缩短/变慢/持平 |
|---|---:|---:|---:|---|
| Mesh | 0.957496 | 0.884502 | 2.294922 | 4/16/10 |
| HiBand FG | 0.957496 | 0.884502 | 2.294922 | 4/16/10 |
| HiBand GB | 0.999604 | 1.001022 | 0.998982 | 17/7/6 |
| HiBand LB | 1.002347 | 1.000324 | 1.031973 | 15/14/1 |

类型优先在Mesh/FG中降低GetS尾延迟，同时推迟MoE及汇合；不能只用GetS指标宣称总体收益。详见[全量审计](FULL_INDEPENDENT_AUDIT.json)、[逐组配对](FULL_INDEPENDENT_PAIRED_RUNS.csv)、[逐阶段配对](FULL_INDEPENDENT_PAIRED_PHASES.csv)。旧双平面RR对新优先Mesh改变了仲裁和平面，只是诊断，不是统一仲裁口径的正式对比。

这些是已用开发用例、合成只读GetS和元数据驱动MoE通信，阶段分别初始化；不是留出、完整一致性协议、数值MoE推理或端到端时间。1ns是模拟参数，不是物理时序认证；本包没有面积/功耗/布线验收，也不套用旧22.13%面积数字。

## 保留的失败与后处理错误

早期缺包含路径的编译失败，以及SV事件探针在81时间单位的优先级断言失败均保留；后者根因未确认。后续C++探针及共同回归通过不能擦除该失败。见[编译失败快照](BOOTSTRAP_FAILED_STATUS.json)与[SV失败快照](SV_PROBE_FAILED_STATUS.json)。

全量仿真MATRIX为PASS，但原audit_full.py错误地在扩展目录查BUILD.json，实际文件在复用的预检目录，因此原驱动后处理退出失败。原[FAILURE.json](execution_sources/full/FAILURE.json)、[audit_full.py](execution_sources/full/audit_full.py)和[驱动日志](execution_sources/full/DRIVER.log)原样保留。全120组的独立本地审计使用真实预检BUILD并通过。未修改远端或重启实验。historical_workflow/extend_full.py包含后来为未来包准备的路径修正，与实际执行的旧脚本明确分开。

## 离线复核与文件索引

在本目录运行 `python verify_bundle.py`，仅检查文件、冻结输入、源码、结果与配对快照哈希。运行 `python verify_results.py --full` 重新做120组/720阶段/5339项账本审计；不调用Docker、SSH、仿真或综合。该脚本将原本机相邻目录的基线快照路径改为包内evidence/BASELINE_SNAPSHOT.json，输出报告写入audit_output/（可用--output-dir指定），保留冻结回执；审计检查逻辑不变。24组预检可用 `python verify_results.py` 单独复核。静态检查为 `python l1_static_audit.py`，会重新生成L1报告。

PACKAGE_MANIFEST.json列出发布字节的SHA-256。LATEST_STATUS.json/FULL_LATEST_STATUS.json是采集快照，含当时实际源码/二进制哈希；它们不意味着下载后重新构建过二进制。receipts/按部署身份分开，根目录旧回执为历史，不应覆盖身份子目录的成功回执。execution_sources/保存实际执行脚本及小型日志；historical_workflow/保存本机部署/采集脚本，仅供溯源，包含原机器路径，不能批量执行。

源码重建与仿真参数可由BUILD.json中的verilator/make命令和MATRIX.json中逐组Docker命令审查，工具镜像sha256:1b0d9532209adf5c7a7b55770167571ab7c109931d53cbbeed74cc8b0fc1dcfe，Verilator5.006、g++12.2。迁移需在另行授权的新空目录映射package/和cases/，恢复相同工具；镜像digest不保证其他机器已缓存或可拉取。不直接运行原驱动，不覆盖本包结果，不重复已有实验。本次只验证发布包离线审计，没有再次构建/仿真。

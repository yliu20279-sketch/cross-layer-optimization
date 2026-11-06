# swe_qwen3：执行器审查后的实施顺序

2026-10-27用户修订：后续步骤3按[参考数据与agent验收分线计划](../swe_qwen3_step3_reference_replan_20261027_v1/PLAN.md)执行。SWE成功不再作为真实fixture复用、算子映射与步骤4功能验证的门槛；GPU仅参考设备。已做真实CPU子链及路由映射初检，存在数值/TopK差异，均保留不判PASS。下文原“GPU基准”及修复准入描述作为历史顺序，不覆盖本次分线约束。

步骤3最终执行回执（2026-10-27核验）：[冻结留出报告](../swe_qwen3_step3_holdout_20261026_v1/REPORT.md)已完成两开发＋两冻结留出采集、官方评分与本地交付，四例均未修复；步骤3工作完成不等于功能准入通过。留出正文读取已获用户明确批准并在方法冻结后执行，gold/隐藏测试继续隔离；不得再以旧权限拒绝停工。当前方法NO_PROMOTION，变更后须另选未读留出；步骤4真实fixture可独立数值核查，目标BF16时序/收益仍未认证。

步骤3后续修订：[诊断与开发验收](../swe_qwen3_step3_development_20261026_v6/REPORT.md)已绑定原BF16 GPU后端并采集真实分块prefill/decode路由与第0层KV fixture；两开发官方0/2、空补丁，当前agent策略未准入，整体PARTIAL。最长实际prompt18213、峰值allocated64.69GB，非完整32K或目标时序认证。原BF16/host128/HB8约束不变；留出正文未读，等待自动审批拒绝后的明确范围批准。下文“未运行/下一步1—2”为原规划时快照，当前状态以STATUS.json及上述报告为准。

步骤1—2后续交付：[BF16逐算子合同与隔离CPU功能适配器](../swe_qwen3_bf16_functional_v1_20261026/REPORT.md)。51项同CPU合成检查通过，实际GPU绑定/真实fixture/完整层与目标时序仍未通过，不升级为整模型BF16认证。

本文件为当前实施顺序，承接PLAN.md及USER_FIXED_CONSTRAINTS.json。固定128 GiB host＋8 GiB HB、原Qwen3 BF16，不用W4/INT4，不转换FP16模型。目标host容量扩展明确标注；本轮只重排步骤，不启动运行。

依据：../swe_qwen3_bf16_executor_audit_20261026_v1/REPORT.md。codec与部分CPU功能参考可复用；全局BF16舍入不能表达源模型，通用算子不全；旧COMPUTE是时序节点，没有BF16原生吞吐证明。功能正确不自动认证目标硬件/时序。

## 1. 固定源码、执行路径和逐算子数值合同

固定模型、tokenizer、Transformers、agent和目标库版本，列每个tensor/op的输入/输出dtype、内部精度、舍入位置和归约顺序。优先明确router的FP32 softmax→Top8→归一化→BF16，RMSNorm的cast-before-scale，RoPE的FP32频率/三角函数，以及expert combine顺序。GPU kernel的实际归约细节未知处不得编造成唯一硬件真值；预先冻结逐阶段比较规则。

交付：OP_DTYPE_AND_ROUNDING_CONTRACT、SOURCE_BINDINGS。通过：没有用全局BF16代替混合精度，没有FP16模型替换，源后端版本可复现。

## 2. 新建隔离BF16功能适配器

复用已验codec与适用的FP32函数，不改旧执行器；补逐tensor/op精度边界、cast、TopK、gather/scatter/index_add、RoPE和KV状态。不能只给通用runtime全局activation_dtype=bf16。FP32常量不全部当BF16权重处理；保留整数语义。

此适配器首先是CPU上的BF16语义参考，不称目标原生BF16运算。测试边界、非有限值、TopK平局、路由权重/ID与真实fixture；修复原审查的Softmax/RMSNorm反例，但不能只针对反例特判。

交付：BF16_FUNCTIONAL_ADAPTER、OP_NUMERIC_CHECKS；先单op和router/expert子链，不加载完整模型做大测试。

## 3. 独立建立真实BF16 GPU基准与采集链

资源核查后用本线隔离环境加载原模型，短生成→临时小仓库自主命令/修改/测试/反馈→预登记SWE开发任务。先开发后留出，固定2开发＋2留出作为pilot；hidden tests/gold patch不进入agent。记录失败、patch与官方harness。

捕获同源layer输入、weight引用、router最终选择与权重、输出及必要FP32中间值，供步骤2/4对比。不能从旧teacher-forced轨迹或gold patch造输入。该步骤不必等完整目标时序实现，但只提供GPU功能证据。

交付：BF16_GPU_BASELINE、TASK_MANIFEST、REAL_FIXTURES、采集开/关扰动报告。

## 4. 完成单层、两层的BF16语义验收

按实际fixture验证attention完整子链、MoE完整子链、单层再两层，包含embedding/head相关边界；不要仅验证专家GEMM。比较输入/输出、实际route、归一化、KV与残差；对源GPU差异和对独立功能合同差异分别记账，不事后放宽容差。目标功能不等价时可继续诊断，不能声称任务已在目标架构完成。

交付：LAYER_NUMERIC_ACCEPTANCE与失败明细。未过时不开展四方案性能结论。

## 5. 冻结BF16目标时序路径及并行/存储实现

功能与时序分开：已查规范未声明BF16阵列吞吐，不能把FP16的2048 MAC/cycle赋给BF16。若不改现有硬件，用现有FP32向量原语的软件BF16路径必须显式实现、逐原语计数，并验证转换/工作区/服务成本；若做BF16阵列假设，只能另列架构扩展敏感性，不能当当前架构已支持。没有合法目标服务路径则保持TIMING_BLOCKED，不编周期。

冻结TP/EP与KV复制、逐rank容量、4 MiB SRAM tiling、地址及32 B事务。实现host完整只读后备＋HB在线共享LRU、pending miss合并、last-reader保护和clean eviction免D2H；KV/activation另外管理。计host DRAM、PCIe、gateway、staging和commit服务。host128/HB8配置与所有四组相同；原W4字节/离线未来状态不复用。

交付：BF16_TARGET_SERVICE_CONTRACT、PARALLELISM_MANIFEST、RESIDENCY/SRAM/ADDRESS账本、ONLINE_PAGER。先事件/字节/容量微测，通过后才有目标周期依据。

## 6. 采完整会话并实例化可执行任务图

记录实际prefill/decode、缓存复用/重算、token/turn/forward身份、每层expert槽/最终权重、工具命令/开始/完成/反馈。展开有限图，不虚构固定读改测次序或额外first-decode。工具完成后才能release下一turn；真实到达与固定时长外部服务回放分开标注。

符号图只有结构检查结果；这里才加入实际T/P/J/m_e、地址、DMA、collective和可执行节点，并逐项绑定真实记录。

交付：REAL_ROUTE_AND_TOOL_TRACE、EXECUTABLE_DAG、token/route/依赖审计。

## 7. 接通功能与目标事件，完成最小片段

先单NPU算子，再层内多NPU、两层和一个工具前后片段。张量只有在数值已产生且对应计算/存储/NET回调完成后才对消费者可见。核对DMA、HB、NoC、工具release、容量与全部依赖；不能把离线计算耗时简单加到仿真总时间。

产物：COUPLED_FRAGMENT_ACCEPTANCE。CPU求值＋原生事件是数值/事件代理，物理NPU与完整在线系统认证另列。

## 8. 实现Sem-MoE与HiBand机制

Sem-MoE先按论文与现有实现做差异表，再用开发任务画像冻结placement/预测器；实际dispatch可读已经产生的router结果，admission/未来层预测不得提前读取真实路由。只有放置时标style placement proxy，不称完整论文系统。

HiBand明确phase/scope/mode，用当前队列驱动合法模式，计drain/setup/switch与剩余服务，完成回调驱动消费者。只有真实BSA/BGA独立区域重叠才报告HIC收益；没有机会保留零。项目local/global抽象不称作者物理split-Benes。

产物：ALGORITHM_GAP、NO_FUTURE_INFORMATION_AUDIT、MODE_AND_SERVICE_EVENTS及机制微测。

## 9. 四方案配对，先开发片段再完整任务

B0 baseline EP，B1 Sem-MoE-only，B2 HiBand-only，B3组合。名称以manifest固定，不与旧方案编号混写。四组同BF16、同实际轨迹/算术合同、同host128/HB8、分页、初始化、工具时长与到达；只改变机制允许的映射/调度/模式，并计其成本。

先一个开发工具前后片段四组，再一个开发完整任务；预算审查后才继续其余case，留出前冻结方法。失败与无加速同样保留。固定轨迹只比较同一路径的目标时序，不声称四组修复率不同。

## 10. 小规模自然并发与最终结论

从1任务到2任务，保留真实提交和工具等待，权重全局共享、KV按session计；不把turn人为设同时到达。报告GPU功能/harness、目标prefill/decode/任务周期、NoC/分页/切换、严格Bank关键路径敏感性与净成本。Bank使用全事务片段或已验收采样，反事实先过微测；旧采样撤回数值不继承。热实验独立后置。

最终分别判定功能完成、目标数值、目标事件/时序、完整任务回放、在线闭环、净收益；任一级失败不提升整体PASS。当前下一步是步骤1和2，步骤3可独立准备；BF16目标时序仍是明确门槛。

# swe_qwen3：BF16 Sem-MoE＋HiBand实现步骤

执行器核查后的当前顺序见[计划修订2](PLAN_V2_AFTER_EXECUTOR_AUDIT.md)。本文件保留核查前九步记录。

步骤1核查已完成：[执行器BF16审查](../swe_qwen3_bf16_executor_audit_20261026_v1/REPORT.md)确认codec与部分host功能参考支持，但全局舍入不匹配Qwen3混合精度，通用op覆盖不足、BF16目标时序未证明。下一步补逐op语义合同和隔离BF16适配器；不能跳到四方案运行。核查含微型CPU源码探针，无Qwen模型或仿真运行。

日期：2026-10-26。状态：PLAN_ONLY；无安装、训练、推理或新仿真。本计划承接算子拆分和旧存储审查，作为当前`swe_qwen3`统一执行入口。旧W4解析路径只作错误排查参考，不能进入本benchmark的权重、流量、容量或周期计算。


用户后续已明确固定128 GiB host＋8 GiB HB及原Qwen3 BF16，见USER_FIXED_CONSTRAINTS.json。该组合是当前主线固定配置；下文原规范host8的讨论只保留历史边界，不是本轮待选项。

## 一、固定本轮约束

1. benchmark名`swe_qwen3`：mini-SWE-agent＋SWE-bench Lite，后端为已核验Qwen3-30B-A3B BF16，revision ad44e777bcd18fa416d9da3bd8f70d33ebb85d39。保留48层/128专家/Top8、无shared expert和完整非MoE算子。
2. 权重/隐藏状态沿源模型BF16，router softmax、norm内部等按实际源码保留FP32运算与显式BF16回写；不转W4/INT4，不使用GPTQ，不将模型改成FP16，不从Qwen1.5复制字节公式。CPU FP32 golden reference只是验证工具，不自动构成设备执行。
3. 目标NPU/HB/NoC沿当前V3.6：16 NPU，4 MiB SRAM/NPU，总8 GiB HB，每Ni↔CHi一条25.6 GB/s接口，32 B DRAM事务。主线host沿上一轮选定128 GiB显式容量overlay，profile为BF16_HOST128_HB8_READONLY_BACKING_V1；原规范host8 GiB保持不变，不把主线写成未修改规范V3.6。
4. host保留完整只读权重，HB全任务共享专家缓存；clean weight eviction只失效，不D2H。SSD只用于主线启动加载，启动时间分账。所有四方案使用同一存储profile，禁止只给某方案更大的缓存或免费的初始化。
5. “当前目标架构”若要求严格原host8 GiB，主线profile不适用，须单独实现SSD→host cache→HB三级分页；本计划保留该分支为未就绪，不默认为SSD已被建模，更不改用W4来装下模型。

已完成的仅有资产准备、头部/参数核查、源码级任务图/48层符号图和候选TP16/EP16映射。当前真实SWE任务、实际路由与目标执行尚未验收。

## 二、实施顺序与门槛

### 步骤1：核实并实现BF16目标算术路径

先只读定位NPUSim/目标库的数据类型、乘加、累加与舍入实现，不凭FP16阵列规格或“2-byte操作数”认定支持BF16。固定BF16输入/权重的表示、FP32累加/归约、最终BF16舍入及每个op的实际dtype。

若已有BF16路径，先验证实现和对应服务时序。若没有，在现有FP32向量原语上评估显式BF16载入扩展、FP32运算、BF16回写的软件lowering；必须计逐原语工作量、临时存储和数据转换，标软件路径，不沿用FP16 MAC2048/cycle给BF16 GEMM计时。能否保持源模型数值需验证，不因FP32可表示BF16就宣称整网络等价。

若现有原语无法支持或成本无法核算，本步骤保持阻断，后续GPU功能线仍可独立采集；不偷偷增加BF16阵列能力，不降精度。另加硬件BF16能力只能另立架构修订，不能称当前架构结果。

产物：BF16_EXECUTION_CONTRACT、实际源码/二进制hash、dtype/舍入表、最小数值fixture与原语成本表。通过条件：BF16无FP16替换、正确性与目标服务路径均可审计。软件CPU求值＋模拟器事件只称数值/事件代理，不称物理BF16 NPU。

### 步骤2：冻结并行映射、驻留集和分块

比较已画TP16＋四份KV候选与attention TP4＋EP16：只变并行/复制，不改变BF16和模型逻辑。选定后逐rank核算nonexpert、专家cache、KV、metadata、prefill/decode workspace和4 MiB SRAM生命周期；专家一份9 MiB必须tile，不可整体塞SRAM。

以当前TP16候选为审查起点：rank r两Q头、KV头floor(r/4)；Q/K norm各128元素共享；EP16每层每rank8专家；router N0、唯一token origin和必要collective全部计费。不是要求必须保留这套映射；冻结前允许按容量/流量选择，冻结后不能为收益随意改变。

host128与HB8预算对接逐rank地址、32 B事务和cache容量；上下文/并发由实际KV和工作区推出。4096累计cache token、prefill chunk64、32 MiB reserve仅是旧候选初值，未经峰值验证不得当正式上限。

产物：PARALLELISM_MANIFEST、BF16_BYTE_LEDGER、SRAM_LIFETIMES、ADDRESS_LAYOUT。门槛：合法容量与地址，复制/对齐/元数据不漏计，权重payload与实际BF16张量绑定。

### 步骤3：改造真实到达驱动的分页与存储完成门控

在隔离目录移植旧Qwen3 LRU、slot/owner、last-use与回调检查，但全部替换W4公式、离线未来页状态和排他host/HB集合。

明确状态：host canonical长期保留；HB entry为共享只读副本；已释放请求触发miss；同页pending miss合并；等最后消费者完成才可复用slot；H2D/commit完成后才能消费；clean victim失效免回传。KV与activation不能套只读免写回规则。

逻辑expert entry9 MiB、DMA chunk候选64 KiB、PCIe payload256 B、HB transaction32 B分开记账。补host DRAM服务、DMA排队、gateway/staging和HB commit耦合，规范PCIe参数55.04 GB/s/方向、250 ns项目代理不混旧270。HB固定物理延迟未知仍留null，不用服务floor冒充链路传播。

产物：ONLINE_PAGER、STORAGE_EVENTS、DMA/HB/OWNER审计。先微测hit/miss/并发共享miss/活跃victim不可换出/容量拒绝，再与设备回调耦合。微测通过不代表SWE收益。

### 步骤4：独立跑通原BF16 GPU功能链

步骤1—3进行静态实现准备时，可独立准备本线环境；运行前核GPU/CPU/存储，单worker，不修改共享环境。先完整模型短生成，再临时小仓库验证模型发命令→读代码/修改→CPU/container测试→观察反馈→终止。

冻结agent提交、依赖、tokenizer/chat template、thinking/采样/停止/预算设置；不能把用户补丁或gold patch替代模型行为。模型硬件就绪与任务环境就绪分别验证。

然后登记2开发＋2留出任务、dataset revision、repo/base_commit和镜像digest，先开发后留出。隐藏评测测试与gold patch不进入模型上下文。所有失败保存；少量任务仅为pilot，不宣称总体修复率。

产物：BF16_GPU_BASELINE、TASK_MANIFEST、容器身份、真实session/patch/harness回执。GPU时间不换算目标周期。

### 步骤5：采集实际dispatch并把符号图实例化

记录实际prefill和每次decode forward的有效token、P/T/J、缓存复用/重算、每层实际expert槽/ID和最终权重；不重算Top-k代替dispatch，不使用旧teacher-forced trace。FP32 router统计、诊断aux与hook扰动分账。

记录task/session/turn/request/attempt/forward、工具命令、起止/退出/反馈、patch与harness。首个输出token来自prefill logits，后续decode不虚增。展开已绘制的控制循环，生成有限真实DAG，按选定映射绑定地址/通信/页请求。

工具CPU/container不计NPU计算；下一turn只能在工具完成后release。固定工具时长回放与真正实时闭环分别命名。目标工具时长不能由GPU绝对时间戳直接平移成NPU时钟。

产物：TRACE_MANIFEST、ROUTE_TRACE、TOOL_EVENTS、INSTANTIATED_DAG。门槛：token/路由/权重守恒、无提前依赖、真实记录可重建图。

### 步骤6：用BF16真实fixture验证目标完整子链

顺序：GEMM与转换/累加 → Q/K norm/RoPE/GQA/softmax/KV → router/Top8归一化 → SwiGLU/权重乘/index_add → 单层 → 两层 → 一个完整工具前后片段。包含embedding/head/vector/collective，不只回放专家MLP。

使用步骤4—5捕获的同源输入/权重/参考，不用shape相同的替代数据。逐项比较BF16数值、路由、输出和累加/回写；容差先冻结，不根据失败放宽。合成小输入只补边界覆盖，不计真实bmk样本。

产物：NUMERIC_ACCEPTANCE、TRANSACTION/DEPENDENCY/CAPACITY审计。步骤1—3及实际fixture均通过后，才做目标时序；失败在哪一级，结论就停在哪一级。

### 步骤7：实现Sem-MoE与HiBand并证明其身份

Sem-MoE先列论文目标函数/容量/画像/放置/在线调度与现有代码的逐条差异；开发任务画像冻结expert placement和预测器。实际router输出可用于该次合法dispatch，但不能被提前交给request admission/未来层调度当预测结果。部署调度只用当时可知prompt/历史/预测，计预测失败、回退、迁移与维护成本。仅完成放置时必须标Sem-MoE-style placement proxy。

HiBand控制器使用已释放队列/当前local-global负载，phase、scope、mode分字段；实现切换drain/setup/service/完成门控，保持带宽预算。无合法HIC重叠或切换机会时接受零收益，不制造机会。项目local/global参考模型不升级为作者物理split-Benes实现。

产物：ALGORITHM_GAP、ONLINE_INFORMATION_AUDIT、MODE_EVENTS与机制微测。未满足论文/系统边界时不使用“完整SOTA复现”标签。

### 步骤8：BF16同轨迹四对照，先片段后任务

B0 baseline EP，B1 HiBand-only，B2 Sem-MoE-only，B3组合。四组必须使用同BF16模型/实际轨迹/逻辑工作量、相同host128/HB8、分页与初始化、工具时长和到达。放置改变引起的合法通信/分页差异保留，不能改变精度或单独给予免费预热。

先一个开发工具前后片段四组，再一个开发完整任务四组；确认host耗时、日志体积和总预算后再放行剩余预登记case。初始cold定义为host-ready/nonexpert-ready/expert-cold，不冒充全系统SSD冷启动；启动与预热另报并在部署成本中摊销。

产物：PAIRING_AUDIT、四组周期/事件/资源及失败表。固定轨迹回放只比较同任务路径的目标时序，不证明四方案修复成功率不同。BF16功能正确、目标数值正确、四方案时序通过分别验收。

### 步骤9：自然多任务到达、归因与净收益验收

从1任务到2任务，按真实提交/工具反馈驱动到达，不压成周期0同时到达；容量/预算未过不扩大。共享权重、会话KV、请求owner与任务owner分账。

主指标分两组：功能GPU的LLM/工具/任务墙钟及harness；目标回放的prefill/decode/任务makespan、NoC、分页、HB容量、切换/安装/迁移/预测成本。严格Bank用全事务片段或经验证采样，normal/owner-shadow先过微测和配对守恒；旧0.0699%不得继承。热建模独立后置。

只有真实收益超过预登记门槛且计入成本时才给净收益结论；没有收益也完成复现报告，不改算力、地址别名、到达或seed去追正值。完整在线目标工具闭环尚未运行时，只称trace-driven复现。

## 三、当前下一步和停止条件

立即应做步骤1的BF16源码/指令路径核查及步骤2的映射/容量冻结；步骤4的依赖准备可独立进行。本轮只规划，不启动以上运行。

任一项成立则不进入目标大运行：BF16能力/软件原语未证明；峰值容量/地址不合法；host服务/回调未计；图依赖提前；调度使用未来路由；精度或硬件配置在四组间变化。GPU功能线不因目标模拟器阻断被伪称失败，但也不替代目标验收。

## 四、来源

- 源码/模型身份和算子结构：../mini_swe_operator_graph_v3_6_20261026_v1/REPORT.md、source/MODEL_HEADER_AUDIT.json、MAPPING.json、CAPACITY.json。
- 目标硬件：../whisper_operator_inventory/target_architecture_v3_6/target_architecture_v3_6.yaml（只明确FP16 MAC/FP32 vector与host8 GiB）。
- 本线存储决策：../mini_swe_storage_audit_20261026_v1/REPORT.md、STORAGE_CONFIG.json（host128 overlay）。
- 旧Qwen3/Qwen1.5经验与采样修订：../mini_swe_hiband_semmoe_plan_20261026_v1/CONSULTATION_SUMMARY.md、../qwen3_30b_a3b_v3_6_experiment/bank_conflict_v2/STEP4_6_STATUS.md、STEP7_STATUS.md。
- agent官方固定提交与行为：../mini_swe_qwen3_preflight_20261026_v1/SOURCE_MANIFEST.json及official_snapshot/src/minisweagent/agents/default.py。

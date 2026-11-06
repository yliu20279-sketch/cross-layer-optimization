# mini-SWE＋Qwen3：复现步骤修订2

用户后续明确全程保留原BF16、不用W4。当前统一步骤以[swe_qwen3 BF16计划](../swe_qwen3_bf16_plan_20261026_v1/PLAN.md)为准；本文件中的FP16转换备选不再是当前授权路径，旧文保留。

日期：2026-10-26。性质：执行前规划，不新增安装、训练、推理或仿真。本文件细化REPLAN.md，保留旧计划与失败。依据为REPORT.md、CAPACITY.json、VALIDATION.json及两条指定Sem-MoE聊天经验。

后续按用户要求审查旧Qwen3/Qwen1.5存储，已选择[BF16 host128＋HB8研究配置](../mini_swe_storage_audit_20261026_v1/REPORT.md)及STORAGE_CONFIG.json：原8 GiB host规范保留不可行状态，新配置显式扩host、保留HB与BF16，host完整只读后备＋HB共享缓存，clean weight eviction免D2H。容量选择完成，步骤1算术/并行及步骤2实际pager/服务模型仍待验收，不等于已运行。

## 目标和当前起点

目标是先让真实软件修复会话产生可核查的模型/工具轨迹，再在明确的目标架构合同下运行baseline EP、HiBand、Sem-MoE、组合四对照。区分GPU功能、固定轨迹回放、目标算术、在线工具闭环和部署净收益。固定轨迹四方案回放不自行证明目标系统实际完成相同修复。

已完成源码/模型准备、头部核查、静态算子图和候选映射；这些只通过结构门。BF16目标算术、可部署存储、模型加载、真实任务、路由采集和模拟器执行尚未通过。HiBand项目抽象与Sem-MoE-style历史放置不能直接称作者完整复现。

将后续分为两条工作线：目标结构线完成算术/映射/存储；功能采集线保持现有BF16模型完成真实会话。二者可独立准备，避免目标存储未定就阻止获得真实输入；在目标回放前必须同时过门。这里指工作依赖，不授权并发占用GPU或启动多worker。

## 步骤1：冻结复现范围与目标配置

输入：现有算子图、规范V3.6、源码和权重hash。

工作：保留GPU BF16功能基准；检查目标是否能实现BF16，若需要软件转换或改用FP16，另立合同与数值验收，不能默认替换。对比attention TP16＋KV四份复制与attention TP4＋EP16，明确其他NPU参与方式、hidden传输与collective。目标仍以规范8 GiB HB为主；目标host仅8 GiB，不把113服务器RAM带入规格。

交付：PRECISION_CONTRACT、PARALLELISM_DECISION、ARCHITECTURE_MANIFEST。验收：每种精度/复制/端口/Bank层级都有明确身份；未知项列阻断。不能仅由“FP16 MAC”推出支持BF16。

## 步骤2：完成逐rank内存和可执行lowering

工作：按选定映射核对pinned非专家权重、专家缓存、KV、metadata与工作区；分别给prefill分块和decode的tile/lifetime/峰值、地址分配和32 B事务。单专家9 MiB不能整体装入4 MiB SRAM，必须分块。61 GB权重不能由目标8 GiB HB＋8 GiB host全部承载，明确外部存储及其服务，或另列扩大host的配置敏感性，不改写规范硬件。

交付：RESIDENCY_LEDGER、SRAM_LIFETIMES、ADDRESS_AND_TRANSACTION_MANIFEST、BACKING_SERVICE_CONTRACT、可执行IR转换器。验收：无容量溢出、重叠地址、隐性零成本搬移；每个存储对象和消费者都有完成门控。原1595节点符号图不是此处的可执行IR。

## 步骤3：在GPU跑通真实自主工具闭环

此项可在步骤1—2仍做静态准备时独立推进，运行前重新检查资源。

工作：本线隔离环境，先模型类/tokenizer与完整模型最短生成，再在临时小仓库验证read→edit→test→feedback。之后固定2个development任务和2个独立test任务，记录dataset revision、repo/base_commit和镜像digest；先运行development，留出题面不用于调提示。隐藏测试与gold patch不进入agent上下文。

交付：环境锁、任务/模型/镜像manifest、会话/patch、工具输出与官方harness回执。验收：真实自主命令与测试反馈闭环；修复失败也是有效结果，不靠人工补丁冒充成功。2+2只验流程，不估总体修复率。任务环境失败与未修复分开记录。

## 步骤4：采集真实路由并实例化任务图

工作：记录实际prefill/decode的task/session/turn/request/forward/token身份、真实expert槽/ID与最终权重、T/P/J/m_e、KV复用/重算、所有工具开始/完成。不要只记录decode，不重算Top-k替代真实dispatch。先做development的采集开/关扰动检查；固定采集代码和方法后再使用test。

展开应用控制循环，绑定实际命令与依赖。首次输出token来自prefill的logits，不能多加一次不存在的decode forward。工具回放若按“前一目标LLM完成＋观测工具耗时”释放下一轮，应标外部服务时长固定假设，不称实时工具闭环。

交付：完整事件/路由表、TRACE_VALIDATION、实际图。验收：有效token与每层Top8覆盖、ID/权重守恒、有限图无环、工具无提前release；所有省略/重算与采集成本可查。

## 步骤5：按真实fixture验证目标算子与耦合

前置：步骤1—2与步骤3—4相关fixture均完成；准备期可用标明合成的小输入做接口微测，但不能替代此步真实fixture验收。

顺序：GEMM/共享QK norm/RoPE/GQA/softmax → router/Top8/专家SwiGLU/combine → 单层 → 两层 → 工具前后片段。分别检验数值、路由、地址/事务、SRAM/HB容量、分页及NoC/Ramulator回调和依赖。先单NPU子算子，再多NPU层内通信。

交付：NUMERICAL_CHECKS、CALLBACK_AND_DEPENDENCY_AUDIT、CAPACITY_AUDIT、失败记录。验收：每个合同独立通过；CPU求值＋设备事件不能称物理NPU执行。target FP16与source BF16不一致时保留差异，固定轨迹代理不得冒充连续网络等价。此步未过，不扩大目标任务。

## 步骤6：实现并验证HiBand和Sem-MoE机制

HiBand：phase/mode/scope分开；使用当前已释放流量驱动合法local/global模式；显式计drain/setup/switch、非零服务与回调。HIC须有真实合法BSA/BGA重叠，正式负载无机会时允许零收益。

Sem-MoE：先列论文算法与现有代码差异，验证目标函数/容量/放置；只用开发任务画像冻结placement与预测器。在线请求调度只能看已知prompt/历史和预测，不能看当前/未来真实专家路由。固定轨迹执行本身可以使用真实route以模拟实际dispatch，但不能把它交给调度器当先验。预测、负载均衡、回退、迁移和安装维护成本分账。

交付：机制差异说明、微测、在线信息依赖审计。未补齐论文调度时明确标Sem-MoE-style placement proxy；HiBand项目抽象不宣称物理split-Benes认证。

## 步骤7：同轨迹四对照，先片段再任务

方案：B0 baseline EP、B1 HiBand、B2 Sem-MoE、B3组合。固定模型/任务/token/实际路由、目标数值合同、硬件、初始化、到达、工具耗时和种子。B0/B1与B2/B3只改HiBand控制，B0/B2的合法放置变化计入通信与分页。

先一个development完整工具前后片段四组；通过后一个development完整任务四组，实测运行成本后再决定其余任务。2+2全做四组是16个逻辑比较单元，不是已授权立即启动16个大运行；重复次数、超时和总预算在启动前冻结。若只能完成片段，结论只限片段。

交付：四组差异清单、运行日志、守恒审计、分项时间表。报告GPU功能修复结果与目标回放周期，固定轨迹回放不声称四方案修复率变化。无加速亦保留结果，不改负载制造收益。

## 步骤8：多任务到达、归因与最终验收

从1任务到2任务，只有资源和运行成本通过后才增加。保留真实提交和工具等待导致的到达，不将所有turn压到周期0。单请求、随机/Bank-balanced与owner-shadow用于机制反例；全事务或验收通过的采样才支持严格Bank归因。已知旧采样不收敛，不能继承旧0.0699%为正式数值。

分别报告：prefill/decode、LLM总时间、工具/队列等待、任务端到端、harness结果；目标NoC/DRAM/分页、容量、严格Bank等待和关键路径敏感性；安装/迁移/切换/控制净成本。跨任务和同任务跨turn owner口径明确。

最终分级：GPU功能完成／目标片段数值与因果完成／完整任务回放完成／在线目标闭环完成／净收益通过，逐项判定，不相互替代。当前缺少本架构热物理参数，热复现另立后续协议，不夹入本轮主结论。

## 现在实际应做的第一件事

完成步骤1的PRECISION_CONTRACT和PARALLELISM_DECISION，并据此补步骤2的逐rank容量与后备存储合同。已下载的模型和已画图谱直接作为输入，不重下权重、不从完整矩阵开始。

## 来源

- 本轮结构与容量：REPORT.md、CAPACITY.json、MAPPING.json、VALIDATION.json。
- 当前模型身份：source/MODEL_HEADER_AUDIT.json、../mini_swe_hiband_semmoe_plan_20261026_v1/ASSET_COMPLETION_REMOTE.json。
- 目标规格：../whisper_operator_inventory/target_architecture_v3_6/target_architecture_v3_6.yaml。
- 既有复现经验：../mini_swe_hiband_semmoe_plan_20261026_v1/CONSULTATION_SUMMARY.md及两份EXPERIENCE文件。
- 采样修订：../qwen3_30b_a3b_v3_6_experiment/bank_conflict_v2/STEP4_6_STATUS.md、STEP7_STATUS.md。

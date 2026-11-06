# LingBot步骤4续作：CPU专家软件核与FP32特殊函数定位

日期：2026-10-29。目录沿用暂停前v3名称。总体状态PARTIAL_STEP4_NOT_COMPLETE，**步骤4尚未完成**。本轮完成了可调用的有限CPU软件适配器及数值缺口定位，未放宽原严格逐位门，未把GPU或Golden注入作为目标回退。原混合BF16/FP32、host128GiB/HB8GiB、目标GPU0、refiner排除；原host8规范不改。

| 层0原语/合同 | 本轮结果 | 范围 |
|---|---|---|
| BF16专家独立C矩阵＋SiLU/乘法 | 935阶段、5898240元素对单线程CPU源逐位一致 | 已见两CFG，各64真实token；非GPU/NPU全层PASS |
| 记录路由MoE合成 | 两CFG各64×2048，CPU源0差异 | 原ID/weight是显式replay诊断，非自主router |
| RMS mean(square) FP32 | 197738行对原GPU逐位一致 | 四个完整postnorm输入，H2048 |
| rsqrt正确RNE | 197738个整数中点区间检查通过，但对GPU因子41631不同 | 最终BF16 postnorm仍1314元素不同，未接入严格GPU路径 |
| sigmoid的FP32 add/div | 给定GPU exp时12655232 score及后处理逐位一致 | 隔离诊断，不是自主CPU exp/sigmoid通过 |
| GPU-equivalent exp候选 | 本机libdevice范围归约＋host exp2仍7权重不同 | CUDA12.8材料不等于原Torch CUDA12.4实现；未采纳 |


## 1. BF16专家功能修复与可调用接口

[适配器](mixed_host_adapter.py)调用独立C实现[source_bf16_gemm.cpp](source_bf16_gemm.cpp)：原BF16输入/权重位模式解码后按源CPU顺序执行FP32乘加，在原边界RNE回BF16；不把checkpoint替换FP32，不使用FP16吞吐。SiLU为显式host FP32软件函数，逐层乘法后回BF16，保持原存储/舍入边界。FP32 linear仍明确是host CPU fallback，GPU数值门未通过，cycles为null。

首轮4线程比较935项中295项不同；该源软件合同依赖单线程oneDNN累加分块，不能把其他工作线的通过直接继承。冻结单线程合同后，真实LingBot gate/up/SiLU/product/down共935阶段、5898240元素对独立Torch CPU源全部逐位一致。之后通过适配器API及最终防护版再次核验，保持0差异。它们是同一已见样例的多阶段检查，不是935个独立样例或成功率。

数据：[四线程失败](server_evidence/primitive_attempt1/RESULT.json)、[单线程核对](server_evidence/primitive_attempt2_singlethread/RESULT.json)、[最终适配器核对](server_evidence/adapter_attempt2_guarded/RESULT.json)。依据为既有oneDNN v3.5.3源码顺序，原始链接：[oneDNN gemm](https://github.com/oneapi-src/oneDNN/tree/v3.5.3/src/cpu/x64/gemm)。本轮相关原checkpoint分片重新核SHA，见WEIGHT_SHARDS；每个真实输入亦绑定步骤3文件SHA。

[CERTIFIED_GEOMETRIES.json](server_evidence/CERTIFIED_GEOMETRIES.json)仅准入本轮观察到的56个无bias M/N/K组合。未知形状、BF16 bias融合边界、错线程、错dtype/形状、非CPU、非有限codec及未实现的严格GPU特殊函数均显式拒绝。不是通用BF16 GEMM或完整层实现。新增12项负对照全部拒绝，未借CPU通过取消GPU门。

CPU记录路由MoE在两CFG的128个输出行共262144元素对CPU源逐位一致；对原GPU仍分别1657/2052元素不同，max_abs分别0.5/1.0，未接受。没有把这个route-known结果作为自由router或完整MoE的GPU认证。

## 2. RMS归约已对齐，rsqrt未对齐

按固定Torch2.6 [Reduce.cuh](https://github.com/pytorch/pytorch/blob/v2.6.0/aten/src/ATen/native/cuda/Reduce.cuh)重建H2048输入的4路累加、32-lane归约及均值投影。一次外部原源码数学诊断保存了FP32 mean、加eps分母和rsqrt因子；四个RMSNorm输出均与步骤3旧Golden逐位一致，手动分解也与原模块一致，因此不是用新参考替换旧失败。

重建CPU mean在四次完整postnorm的197738行上与原GPU FP32 mean逐位一致。独立NumPy从全部原BF16输入重新求平方/归约，再次逐位一致。该均值函数可独立复用，不等于整个RMSNorm已通过；Q/K head宽128及其他norm几何未由此获得认证。

[rsqrt_rne.cpp](rsqrt_rne.cpp)用FP32输入/输出及128位整数中点比较实现正确RNE，不使用FP64模型算术；197738次整数舍入区间检查通过。但原GPU rsqrt因子有41631个不同，最终原BF16 postnorm仍为正CFG386/301、负CFG333/294，共1314元素不同，未接入严格GPU接口。[RSQRT_RESULT](server_evidence/RSQRT_RESULT.json)、[位模式反例](server_evidence/RSQRT_COUNTEREXAMPLES.json)保留。

NVIDIA [PTX8.4 rsqrt说明](https://docs.nvidia.com/cuda/archive/12.4.1/parallel-thread-execution/index.html#floating-point-instructions-rsqrt)为近似形式给出精度要求，不能据“同为FP32”推导CPU正确RNE与GPU位模式相同。本轮证据确认了两者不等；尚未实现并认证原GPU特殊函数的位级CPU路径，不把更准确的数学结果当作原源码结果。

## 3. sigmoid误差限定到exp，仍不准入自主router

外部诊断的两份GPU sigmoid输出与步骤3FP32 scores全部逐位一致，GPU分离exp/add/reciprocal亦相同。读取源GPU exp仅作隔离诊断时，独立C的FP32 add/div和独立NumPy都在12655232个score上逐位一致，随后Top8槽位及790952个BF16权重亦无差异。见[FINISH_RESULT](server_evidence/FINISH_RESULT.json)。这把当前同logits的CPU sigmoid缺口限定到了exp实现，**不是**把GPU exp作为目标可调用实现。

本机CUDA12.8 libdevice IR中expf范围归约最终调用近似exp2；本轮移植范围归约并以host exp2替代后仍有7个权重差异，候选未采纳。已安装CUDA12.8的IR不是原Torch2.6/cu124编译材料的同一性证明。见[RANGE_EXPF_PROBE](server_evidence/RANGE_EXPF_PROBE.json)及[材料绑定](server_evidence/DEVELOPMENT_BINDING.json)；[PTX8.4 ex2说明](https://docs.nvidia.com/cuda/archive/12.4.1/parallel-thread-execution/index.html#floating-point-instructions-ex2)不提供可直接替代的CPU位级算法。

旧v2同logits→CPU sigmoid的6权重差异、自由CPU GEMM/sigmoid的93差异继续保留；本轮并未修复自主FP32 router GEMM。不能用给定exp/score后的通过，替代自主sigmoid/router通过。

## 4. 外部参考、目标执行和审计分账

新增一次外部GPU1数学诊断，仅原RMSNorm四次、sigmoid两次，完整模型推理调用0、目标GPU0。峰值allocated 1636282368 B、约13.06s；所有六项输出与旧Golden一致。参考任务已退出，后来观察到的两个lintian用户vLLM进程并非本任务，未操作。没有修改共享环境/驱动或加载完整模型/下载refiner。

本地SSH等待曾返回1而未取得独立远端退出文件；源RESULT与六项原值完整，数值数据由独立审计复核。此传输/退出异常未重写为退出0，记录在[RUN_OBSERVATIONS](server_evidence/RUN_OBSERVATIONS.json)。它不被用作进程管理PASS。范围归约和正确RNE为开发追加，代码/二进制封存，不称预登记独立留出验证。

本轮新NPUSim0、Sniper0、物理NPU0；LingBot累计仍仅此前一个FP32 router片段，其对GPU121/128不同的失败不撤销。无新NoC、pager、HB/SRAM生命周期或完整host服务时序；所有CPU软件fallback的目标成本仍未计费。

[独立审计](server_evidence/INDEPENDENT_AUDIT.json)共532检查0失败、12负对照；重算专家聚合输出、完整均值、给定exp后的score，并核对冻结代码/输入/分片SHA。审计状态为PASS_LIMITED_EVIDENCE_AUDIT_OVERALL_STEP4_PARTIAL，指证据及限定原语通过，不是全层数值通过。

## 5. 尚未完成的步骤4门

1. GPU-equivalent exp/rsqrt位级host软件原语；不能用行号查表、原中间值注入或GPU目标回退替代。
2. GPU-equivalent FP32 router GEMM及BF16投影/专家累加顺序；当前CPU源专家通过不等于GPU通过。
3. bias融合、Q/K norm及FlashAttention特殊函数/归约边界，以及新适配器的完整DiT层连续闭链。旧v2完整上下文64查询行的attention/串联block差异保留，本轮未宣称重跑新完整层通过。
4. 原计划的条件编码器/VAE软件合同和完整TI2V目标链仍未完成；不称端到端适配完成。HB/NoC/host边界及策略矩阵仍需后续独立门。

在这些门未通过前，步骤4不能标完成，也不晋级HiBand/Sem-MoE性能/收益矩阵；未修改验收阈值。

## 6. 交付范围

完整本轮输出留113：/mnt/sda1/h3240101068/lingbot_step4_completion_20261028_v3。清单记录296载荷、2637848879 B；[全输出SHA](server_evidence/FULL_OUTPUT_MANIFEST.json)不含外层包、工作日志及libdevice.ll，后者单列材料SHA。

本地仅审阅子集：281载荷、106827655 B，压缩包83854093 B、SHA256=948d05093ee852673ebabd04ce5b4859d3b8837b8ff679daf3fbcf0732b4245c，外层与全部成员核验通过，见[LOCAL_VERIFICATION](LOCAL_VERIFICATION.json)。包含全部代码/冻结/失败、C库、完整专家聚合输出、均值/因子和小型exp切片；完整大norm输出及GPU exp仍留113。旧v1/v2目录与历史证据未覆盖。

# swe_qwen3：第三步重规划与目标功能推进

日期：2026-10-27。用户要求将参考数据采集与agent修复验收分开。原BF16、host128 GiB＋HB8 GiB overlay保持；目标没有GPU。GPU仅是已有源模型参考运行平台，不是目标设备。旧失败/评分/冻结/协议均保留，本文件修订后续工作依赖。

## 1. 两条独立验收线

3A参考数据线：同checkpoint/source/backend身份、输入/权重引用/输出/实际dispatch/缓存状态/工具依赖可追溯，数据文件完整且覆盖可说明，即可逐op消费。任务修复失败不自动否定真实算术数据；也不能把失败轨迹当成功任务代表。

3B agent线：保留小仓库和SWE开发/留出官方修复验收。结果单独记账，不再作为3A、算子映射或目标功能验证的前置门槛。本轮不启动新agent候选、不追加修复重试、不新增留出采集；已有v4/v5有界后台运行与评分保留，不因本次规划终止/移动/改写进程。已有门控仍不得因开发失败读取新留出。若后续确需成功任务端到端声明，再单独完成3B，不拿已有失败路径替代。

新的依赖：已有采集核查→逐op映射/数据覆盖表→真实op与子链→完整单层→两层→目标事件/存储/通信；3B作为旁路报告。参考采集与目标运行分开，不要求目标中存在GPU。

## 2. 已有数据复用结论

来源包：原短生成/小仓库11次capture-on请求；Oct26 v6开发29次实际请求；旧Astropy留出46次实际请求。数量来自各原CAPTURE_AUDIT/REPORT，不是本轮全部重新验包。原本地SHA回执继续有效；本轮只重新核查固定三个请求的REQUEST、route、fixture，共9文件，均与原请求manifest匹配。不挑选修复成功样例；没有访问任何新留出正文、gold或隐藏测试。

| 数据 | 可直接用于 | 不足与限制 |
|---|---|---|
| 原短生成R0002，19-token prefill＋首decode | 最小输入输出、router、残差/norm、真实路由调试 | 旧版无首decode缓存快照；完整attention需由prefill顺序重建并核对 |
| v6开发R0001，738-token分块prefill＋首decode | 当前优先开发fixture；真实KV状态、层0attention/MoE边界、所有层路由 | 不是每个op中间量，也不是48层完整激活快照；完整单层仍未数值认证 |
| 旧留出R0001 | 历史采集可用性核查与以后明确标注的已使用数据回归 | 已被查看/评测，不再是新留出；本轮没有用它调整CPU功能实现 |
| v2—v5新agent开发 | 请求/工具交互诊断 | 开发capture关闭，不能替代有route/fixture的旧采集；不得为收集这些数据重复跑SWE |

同checkpoint权重不是每份fixture里复制61GB，而是FIXTURE_WEIGHT_BINDINGS按key、分片SHA、index/config绑定。本轮仅按key载入一个真实norm向量，不重新加载整模型，也未重新计算所有61GB分片SHA。后续各算子需核验其确切权重key/分片绑定，不能只凭shape复用。

机器清单与逐阶段schema见REUSE_INSPECTION.json。覆盖层0 decoder_input/output、attention_output、moe_input、BF16 router_logits、FP32概率、实际Top8 ID/最终BF16权重、BF16 cos/sin；v6还含首decode前KV。Q/K/V投影及norm/RoPE中间值、各专家gate/up/down输出、LM-head logits、层1输出等缺项必须列明，不假装已保存。

## 3. 本轮已推进的功能与映射

REAL_BOUNDARY_CHECK.json：既有CPU适配器＋原checkpoint层0 post_attention_layernorm.weight，对短生成及v6开发的7阶段做残差相加→RMSNorm与实际moe_input比较。6阶段逐位一致；开发prefill chunk1的524288元素中16个不同，最大绝对差0.0009765625。保持严格比较失败，不事后放宽容差；尚未把差异归因到具体归约指令。其他阶段一致也不证明整层一致。

REUSE_INSPECTION.json：CPU从捕获GPU logits重算FP32 softmax/Top8/renorm。所有12个阶段的slot权重BF16相等，但部分prefill的专家ID顺序及集合不同。短prefill的token14，CPU第8专家100而GPU为26，对应logits同为-4.0625。相同权重不能掩盖专家身份改变；这已经超出“仅排序不同”。跨backend TopK平局语义需单独处理。

两种路径必须区分：固定真实dispatch回放时，使用捕获ID/权重作为已释放的外部输入，验证专家计算/映射；这不算目标router通过。目标自主router路径必须独立验证非平局与边界平局，并预先说明源backend平局规则能否复现；不能为了通过直接注入ID。不得将未来路由提前暴露给在线调度器。

REAL_EP16_MAPPING.json：原短请求与开发首请求各取首prefill和首decode、全部48层，共192条层/forward记录。绑定候选owner=e mod16、每forward token origin=t mod16，给出每专家m_e、rank assignment、origin→owner计数与逻辑payload；逐条sum(m_e)=8T。active_expert_weight_bytes_unique不是必然DMA字节，缓存复用/重读、元数据、包头、对齐、32B事务尚未计入。cycles=null。TP16/KV四份复制仍只是原候选，未冻结为最终并行方案。

以上全部CPU执行，CUDA未初始化，NPU运行0；没有认证目标BF16阵列、吞吐、设备事件或策略收益。

## 4. 后续执行顺序与独立门槛

1. 冻结可消费fixture目录及manifest。优先短R0002、v6开发R0001；旧Astropy仅历史回归分账。按op列输入/权重/输出/缓存/索引与缺项；不再等待SWE resolved。参考门槛以每个fixture覆盖范围判定，不能用一个总PASS代表完整网络。
2. 完成当前差异诊断。拆开残差与norm中间量，区分FP32归约误差和BF16舍入边界；TopK分别核非平局、内部平局、Top8边界平局。保留现有严格失败，跨backend数值规则若需新增版本，必须运行前冻结并保留逐位结果，禁止将ID错误当连续数值误差豁免。
3. 映射逐op到当前V3.6。Q/K/V/O和expert GEMM列BF16载入/FP32累加/回写；norm/RoPE/softmax/SiLU/TopK/索引/合并列FP32 vector/reduce及缺失原语；TP/EP collective、host工具release、host→HB→SRAM门控分开。不能把CPU库实现称目标实现，不给BF16套FP16 2048 MAC/cycle。
4. 按真实数据做attention、router、单专家/MoE、残差子链，再单层与两层。先验证函数边界，再验证TP/EP切分/归约后的结果。每次只载入所需权重，不重跑agent。单层没过时可继续定位其他独立op，不能进入整体PASS。
5. 只补缺失参考数据。优先用已有原输入与checkpoint在隔离CPU参考上重建，并明确其不是原GPU中间真值；如必须绑定实际GPU归约/层1/LM logits，仅一次有界已登记输入的参考forward采集，预核资源、冻结hook与采集合同，不进行自主SWE重试。原数据保持不改。
6. 冻结最终TP/EP、KV复制和tile，核host128/HB8、每rank512MiB CH、4MiB SRAM峰值及地址/32B事务；实例化最小层内DAG。相同route/count不等于容量通过；未建模通信/事务不能冒充可执行DAG。
7. 功能通过后接目标原生事件，按单NPU→层内collective→两层→工具前后片段。存储/计算/NET回调完成才释放消费者。BF16服务路径未证明则TIMING_BLOCKED，仍可继续独立功能验证。随后才进入Sem-MoE/HiBand配对实验，成功任务收益与失败轨迹时序分账。

## 5. 验收状态分别记录

- REFERENCE：本轮抽查成员完整、真实fixture可按范围复用；完整op覆盖仍有缺项。
- NUMERIC：真实CPU子链6/7逐位通过、1失败；router跨backend ID有差异，未准入。
- MAPPING：192实际路由记录候选EP16结构实例化，非设备执行。
- AGENT：既有失败保留，当前v4/v5状态不由本报告预判；不阻塞前三项。
- TARGET：NPU运行0，完整层/BF16服务时序/分页NoC/策略收益均未认证。

## 来源

原报告：../swe_qwen3_step3_gpu_20261026_v1/REPORT.md、../swe_qwen3_step3_development_20261026_v6/REPORT.md、../swe_qwen3_step3_holdout_20261026_v1/REPORT.md及对应CAPTURE_AUDIT/LOCAL_EVIDENCE_VERIFICATION。

适配器与严格合同：../swe_qwen3_bf16_functional_v1_20261026/bf16_adapter.py、NUMERIC_CONTRACT.md、ATTEMPT1_RECEIPT.json。

架构与候选映射：../whisper_operator_inventory/target_architecture_v3_6/target_architecture_v3_6.yaml、../mini_swe_operator_graph_v3_6_20261026_v1/MAPPING.json、REPORT.md；host容量选择见../mini_swe_storage_audit_20261026_v1/STORAGE_CONFIG.json。

本轮机器证据：inspect_reuse.py、validate_real_boundary.py、REUSE_INSPECTION.json、REAL_BOUNDARY_CHECK.json、REAL_EP16_MAPPING.json。本轮未修改原适配器、权重、采集或运行中的agent方法。

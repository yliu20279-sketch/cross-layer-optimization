# mini-SWE-agent 基线准入

状态 PARTIAL。负载固定为 mini-SWE-agent、Qwen3-30B-A3B BF16 与 SWE-bench Lite。

数值候选采用已验收的 v3 连续两层 CPU 语义参考，限定 prefill19/cached decode1。真实任务参考采用 10 月 26 日冻结方法、镜像及官方评分。两开发与两个已用 Astropy 留出均为空补丁，官方 resolved 均为 false。留出不得再次作为新留出。以原 FREEZE.json、BINDING 及权重清单为身份入口，完整权重逐分片核验和请求资产绑定仍是准入项。

系统候选保留 v3 的 16 节点两轮局部证据，host 128 GiB、HB 合计 8 GiB。v7 本地仅有首轮前缀回执。第二轮缓存写回断言及 v8 未启动来自交接，待核对 113 原始退出回执、首个失败序号、脏行地址、提交和完成时间、后继读者及反馈映射。未冻结完整系统 B。

事件最小字段为 task_id、request_id、event_id、parent_ids、phase、shape、dtype、resource、bytes、clock_domain、start_ns、end_ns。任务开始、工具调用和返回、LLM 到达、排队、prefill、逐 token decode、补丁导出和评分分别记录。后续请求保留原始工具返回依赖。CPU、PCIe、缓存、同步和迁移单列资源，重叠按时间区间处理，按依赖和资源等待重建关键路径。分别验收请求服务时间、任务墙钟时间和官方 resolved。

Sem-MoE 需验证实际 Top8 路由、专家归属、输出一致及策略启用回执。HiBand 需验证页面可迁移、目标空间、实际迁移与同步开销及访问生效。完整基线及合入版本通过后再开启正式矩阵和 CA 消融。

## Qwen3 算子与有界验收交接

prefill、首 token decode 和缓存 decode 分别登记。在每层保留 RMSNorm → Q/K/V 投影 → Q/K Norm → RoPE → KV 读写 → QK → softmax → AV → O 投影 → TP 归约 → 残差 → MoE Norm → router（FP32 路径）→ softmax/Top8 → pack/dispatch → gate/up → SiLU×up → down → return → FP32 combine → 残差。第二份咨询列出的 shared expert 不纳入本 Qwen3 候选图，实际算子以冻结模型图为准。权重调入、KV 持有与追加、最后读者和释放单列。mini-SWE 复用模型图，另以工具完成回执解锁后续请求。

TP16 候选按 32 Q 头每 rank 两头、4 KV 头各四份映射审计。EP16 候选按 128 专家每 rank 八个、RR owner = expert mod 16。每 token 只有一个逻辑 origin，每有效 slot 只 dispatch 一次。保留源 expert ID、slot、权重及逆置换，按源次序合并。TP collective 与 EP dispatch/return 分组分账。并行生效须有同一活动域的收发和完成回执。

有界验证先使用已见 prefill19/cached decode1。检查逐阶段 shape/dtype/SHA、Top8 平局、slot 与消息字节守恒、事务末回调和 NoC 尾包门控、KV 与脏行写回释放。统一时钟下记录依赖边与资源等待，分别报告交叠和关键路径。CPU codec、PCIe、DRAM、缓存写回、同步及迁移没有完整回执时保留成本缺项。与 Qwen1.5 共用事件与回调合同的协调仍待完成。

本地 v8 队列回执为 WAITING_V7_STRICT_FINAL_PASS，完整目标运行计数为 0。v7 第二轮约第335次投影触发断言仍为交接信息，等待113原始回执。两份咨询的四组策略配对仅供后续设计，当前维持全套优化合入并准入后的正式实验门槛。

来源：[结构图](../mini_swe_operator_graph_v3_6_20261026_v1/REPORT.md)、[Top8](../swe_qwen3_softmax_top8_20261027_v1/REPORT.md)、[合并顺序](../swe_qwen3_real_ops_cpu_20261027_v1/REPORT.md)、[时钟修订](../swe_qwen3_legosim_clock_fix_20261030_v1/REPORT.md)、[v8队列](../swe_qwen3_lifetime_owned_20261102_v8/QUEUE_STATUS.json)。

## 两份咨询的 mini-SWE 拆分与准入

应用图：issue/repo/base commit → turn/request → 分块 prefill 或实际缓存复用 → 首 token 与逐 token decode → 命令解析 → 文件搜索/读取/编辑或 CPU/容器测试 → 工具输出 → 下一次请求。记录 session、turn、attempt、缓存命中/重算、工具开始/结束/退出码/输出 SHA 和原始到达时间。后续请求同时受外部到达及工具完成门控。固定轨迹与自主闭环分别验收，画像与评估按整个任务隔离，在线策略只使用当时已知数据。

模型图：RMSNorm → Q/K/V 投影 → Q/K Norm → RoPE → KV 读/追加 → QK/softmax/AV → O 与 TP 归约 → 残差 → MoE Norm → router GEMM/softmax/Top8 → pack/EP dispatch → gate/up/SiLU×up/down → EP return → 源顺序 combine → 残差。结构报告确认该 Qwen3 配置无 shared expert，按该配置建图。TP16 每 rank 两 Q 头、每 KV 头四 rank 复制，EP16 每 rank 八专家，e mod 16 为候选 RR。TP 与 EP 分账，PP 需另有实际调度证据。

每个逻辑 token 的每个有效 slot 仅 dispatch 一次。记录源 expert ID、slot、权重、owner 与逆置换，保持实际 Top8 平局顺序和源累加精度。以阶段输入/输出、shape、dtype、SHA 做首差检查。保留 GPU 与 CPU 语义差异，区分回放已保存路由和自主生成路由。

计算须等待 token 与权重就绪。LOAD/STORE 等最后 DRAM 回调，通信等最后分段到达，combine 等全部有效 slot，释放等最后读者及持有权归零。缓存写回分别记录事务 ID、提交顺序和完成时间，时钟按已验收换算规则统一。记录第二轮反馈实际生效和 CPU/host DRAM/PCIe/HB/cache/SRAM Bank 成本；逐项验收字节、DAG、容量及时间守恒。

咨询中的 v7 第335次投影附近及回执顺序解释列为定位线索，未获 113 原始失败记录确认。v8 本地有限验证保留，完整16节点运行待查。四组 Sem-MoE/HiBand 配对作为未来方案，正式对比仍等待全套合入并准入。

来源：[结构报告](../mini_swe_operator_graph_v3_6_20261026_v1/REPORT.md)、[真实算子与顺序](../swe_qwen3_real_ops_cpu_20261027_v1/REPORT.md)、[Top8验收](../swe_qwen3_softmax_top8_20261027_v1/REPORT.md)、[时钟修订](../swe_qwen3_legosim_clock_fix_20261030_v1/REPORT.md)、[v8边界](../swe_qwen3_lifetime_owned_20261102_v8/REPORT.md)、[冻结留出](../swe_qwen3_step3_holdout_20261026_v1/REPORT.md)。

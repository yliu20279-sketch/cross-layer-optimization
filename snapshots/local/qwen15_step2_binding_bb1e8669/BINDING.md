# Qwen1.5 FP16/K64 冻结绑定清单

状态 PARTIAL。范围为 layer 0 的 A/B 开发请求，各含 prefill1 和 cached-decode1。无新运行。

- 结构与 lowering：归档 README.md、build_workload.py、lower_legosim.py、REPORT.md 分别来自本地 qwen1_5_moe_a2_7b_v3_6 与 selector_fp16_joint_native_v1。沿用 PP4×TP4/EP4，保留共享专家、dispatch/combine、tile 回调和 32 B 规范边界。旧合成路由及 256 B overlay 仅保留历史用途。
- v9 参考：ca_p0_1b_q15_k64_20261103_v9/tools/reference_k64_tp_cpu.py，调用见 run_q15_candidate.sh。PROTOCOL.json 规定 FP16 存储、递增 K64 FP32 部分和及 expert ID 升序累加。NUMERICAL_GATE_SCOPED.json 覆盖四阶段逐位一致、槽位一致及 24576 个 KV 元素零差异。保留 v6 原口径差异。
- v11 权重身份：ca_p0_1b_native_20261103_v11/contracts/qwen15*.json，绑定 GPTQ INT4 group128 离线解码 FP16、源与目标指纹、逐张量清单、host 映射、QKV bias 与共享专家 TP 规则。历史合同中的权重指纹沿用其来源。
- 请求状态：两版四个 hidden-state 输入沿用相同哈希。runs/qwen15_dual01 下绑定协议、请求轨迹、阶段、KV 事件和 prefill 后各 rank K/V。轨迹时刻为观测服务时间。A/B 归开发集。
- v11 并发：16 批 KV 读重叠及 40 个成员逐位一致。缺全量 RUNS.sha256，复用限已有覆盖。PP 仅边界载荷探针。
- 待补：上游 revision、源分片到 FP16 的逐载荷独立校验、独立零解包及零量化元数据读取回执、原 token/mask、自然到达、种子及预热状态、独立留出。全模型参考和完整 PP 超出此冻结范围。

远端校验成功时，SOURCES.sha256 绑定 113 来源，FREEZE.sha256 绑定归档自身。以回读校验结果判定交付。

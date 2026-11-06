# 连续两层 ISA/缓存/时钟隔离修订
状态 READY_TO_LAUNCH，非最终通过。
原BF16、host128GiB/HB8GiB、prefill19/cached decode1、连续两层、16NPU保持。
来源swe_qwen3_continuous_portable_20261101_v7，失败原目录保留。
新Sniper补入与冻结副本相同的XED NEHALEM ROI观察器，正例5841次支持/0拒绝，AVX_VXORPS负例被检测。
专用单次write维护事件记录，按CPU AFTER_DRAIN标记合并独立事件流，保留ACK编号、时间、完成门与CPU传输时钟检查。
每轮Sniper统计保存在对应proc目录的sniper_stats，消除两轮SQLite覆盖风险。
原始759个FP32投影逐调用首差即停，最终独立复核759投影/56阶段/12严格输出KV，以及缓存写回、ISA、NoC反馈和统一时钟。
运行36小时上限，独立最终审计2小时上限。依据旧首轮含NoC10小时59分39秒，预计两轮约22小时，余量约14小时；上限不保证完成。
运行入口 python3 run_bounded.py；已有run1时拒绝重复启动。
最终仅以FINAL_DELIVERY.json和相应RAW_ORACLE_AUDIT/CACHE_CHAIN_AUDIT/CLOCK_AUDIT/BASE_INDEPENDENT_AUDIT等回执联合验收。
不构成完整CPU/PCIe/逐MAC成本、物理性能或策略收益认证。正式矩阵0。证据全部留113。

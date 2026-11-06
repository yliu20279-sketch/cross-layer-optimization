# 步骤 6：事务采样收敛最终处理

状态：`RESOLVED_FULL_TRACE_REQUIRED`。

结论不是“4 KiB 已收敛”，而是固定上限采样不适合严格 Bank-conflict timing。后续 Bank 机制与分布证据必须使用完整事务；采样结果不得用于 owner-shadow 端到端差值。

## 为什么原判据不成立

累计严格等待的原始和会随采样事务数增长，不能直接用 S8、S16、S32 的相邻变化判断固定采样是否收敛。更重要的是，Bank 排队具有非线性：减少事务会改变到达相位、Bank 队列和行状态，不能用简单乘权恢复。

## 完整事务参照

使用 c8、同时释放、1 step，在层 0、8、16、24、32、40、47 分别运行：

- 4 KiB 固定采样；
- 1 MiB 固定采样；
- full transaction trace。

共 21 个运行，全部通过操作完成、DAG 依赖、内存回调和字节守恒验证。

1 MiB 相对 full trace：

- Bank traffic 的 Jensen–Shannon divergence 为 0.0029–0.0081，说明访问量分布较接近；
- 每事务严格等待的相对误差为 -100% 到 +54.2%；
- 发生严格等待的事务比例相对误差为 -100% 到 +79.9%。

因此“访问分布接近”不能推出“冲突时序接近”。4 KiB 采样误差更大，并可制造 full trace 中不存在的伪冲突。

## 日志扩展

新增 online Bank aggregate：按 partition、bankgroup、bank 聚合事务数、等待事务数、严格等待 ticks、控制器队列、行命令和完成时间。关闭详细日志后，缩小 c8 full trace 的聚合结果与 893,056 行详细日志逐 Bank 完全一致，而输出仅 257 行。

## 后续使用规则

1. 原 4 KiB 严格等待和原 `0.0699%` 只能保留为历史探索性结果，不能作为最终定量结论。
2. 原因图使用 layer-stratified full trace 数据。
3. 不使用 sampled owner-shadow delta 作为端到端现象图证据。
4. 完整 48 层 full trace 试跑按速度预计需要 2.5–3 小时，超过两小时运行上限，已停止并保留部分日志。
5. 在恢复全模型端到端归因前，需要把 cycle-by-cycle memory driver 改成事件驱动或经 full-trace 分层参照验证的并行 replay。

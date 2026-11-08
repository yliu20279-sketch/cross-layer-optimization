# 全局空闲区间必须进入 DRAM 时钟

原 server 的 `present_cycle` 包含 InterChiplet 的请求/回复与 NPU/NoC 等待，但原 `Ramulator2Wrapper::run()` 内部时钟仅在该次请求尚未完成时 tick。`service_start` 没有传给 wrapper。目标 YAML 又启用了 AllBank refresh，因此不能把两者当作同一条连续时钟。

本隔离版默认保持旧行为。`RAMULATOR_GLOBAL_WALL_CLOCK=1` 时，请求的实际全局 service_start（1 ns 单位）对齐到首个不早于它的 DRAM 边沿（tCK=1.25 ns），空闲期间逐个执行原生 `memory_system->tick()`；不跳过 refresh，不拟合服务时延。完成绝对 DRAM 边沿只转换一次回全局周期，包括边沿对齐等待。

单元参考直接创建 Ramulator2 原生 frontend/memory system，独立用有理数 `5/4` 换算边沿并逐 tick 推进；不调用候选 wrapper 的任何时钟或服务方法。48 条明确人工刺激覆盖跨行/非对齐传输、读写、长空闲、refresh 和错误时钟拒绝。应用接入前另做原生 server 协议与目标 16 NPU+16 Ramulator2 回归。

此前后端的运行仍保留作 back-to-back transactional 模型的接口/容量/固定点验证，不把其周期冒充修复后的连续全局时钟性能。容量、组织、tCK、控制器、地址映射和单逻辑请求并发配置不改；LPDDR5 仍只是 HB-DRAM 命令时序代理，不是工艺校准。

# Qwen3-30B-A3B Bank Conflict v2：步骤 1–3 冻结记录

状态：步骤 1–3 完成。定义与基线已冻结；44 条合成到达轨迹已按现有 c8 事件测得的请求生命周期校准、生成并通过结构与 SHA-256 校验；73 文件 provenance 清单已建立。

## 1. 严格定义

Bank-conflict overhead 指跨 inference request 的同 Bank 竞争：当另一条、属于不同 inference request 的请求占用相同 decoded Bank 时，一条内存请求在 issue 前产生的等待。

计入条件同时满足：

1. 两条请求具有不同 `request_id`；
2. 两条请求解码到同一 DRAM partition 和同一 Bank；
3. 被阻塞请求已经 ready，但尚未 issue；
4. 阻塞原因是该 Bank 被另一 inference request 占用。

明确排除：正常 DRAM service、同请求竞争、row miss/row switch 本身、非 Bank 控制器延迟、NoC、DMA、计算、同步、分页和 DAG 依赖等待。

主要端到端指标：

`strict_bank_fraction = (T_normal - T_owner_shadow) / T_normal`

它是配对反事实敏感度，不是累计 Bank wait，也不天然是可加时间组成。累计严格等待、冲突次数和队列延迟只作为机制指标单独报告。

## 2. 冻结基线

探索性主基线：`ctx128-c8-high-skew`。

长上下文对照：`ctx512-c8-high-skew`。

冻结事实：

- 模型：Qwen3-30B-A3B；
- 架构：v3.6，默认 16 个 DRAM partition；
- 图：48 层、2 个 decode step、microbatch 1；
- 组合：项目内 HiBand + Sem-MoE-inspired 专家摆放；
- 正常组与反事实组必须共享相同 DAG、路由、请求数、计算周期、NoC 数据量、内存字节量、分页序列、二进制和动态库；
- `ctx128-c8-high-skew` 已有正常执行时间 496,197,499 cycles，owner-shadow 配对差值 346,882 cycles，比例 0.069908%；
- 上述候选是事后筛选出的探索性候选，不称为预注册的“最强自然负载”。

冻结后禁止：根据新结果重新选择路由窗口、改变 Bank 定义、移动专家/KV 基址、改变 DRAM timing，或把扩容与 Bank remap 混在同一比较中。

需要在正式运行前补录的哈希：任务图、路由输入、专家摆放、模拟器 binary、Ramulator/相关动态库、配置文件、生成脚本和到达轨迹。

## 3. 请求到达轨迹

目前没有真实线上服务日志，因此本阶段生成的是可复现合成轨迹，不得称为 trace-derived 或真实生产流量。

三类模式：

- `steady`：固定间隔到达，用于控制并发和复现实验；
- `poisson`：指数分布 inter-arrival time，用于无记忆到达对照；
- `bursty`：两状态 Markov-modulated 到达，高负载 burst 与低负载 idle 交替。

并发目标：`c2/c4/c8/c16`。每种随机模式使用种子 `1101, 1102, 1103, 1104, 1105`。steady 使用确定性种子 0。

每个 CSV 字段：

- `request_id`
- `arrival_cycle`
- `target_concurrency`
- `arrival_mode`
- `seed`
- `is_synthetic`

轨迹只决定 inference request 的释放时刻；不得改写请求内部依赖、专家路由、计算量或内存访问量。实际并发是否提高必须在后续由 active request 数、memory overlap 和每 Bank 同时等待 owner 数验证。

## 完成边界

步骤 1：完成。

步骤 2：完成。基线图、运行控制、工具链输入及两组基线证据已写入 `step1_3_provenance.json`。

步骤 3：完成轨迹构造与离线校验。首轮到达间隔以 `ctx128-c8-high-skew` 正常组事件测得的请求生命周期中位数 475,034,142 cycles 按 Little's law 校准。steady、Poisson、bursty 共生成 44 条、5,632 条请求记录。该校准只保证期望在途并发约为 c2/c4/c8/c16；实际并发仍须在后续接入连续请求 DAG 后测量，不能把预测值当作已实现并发。

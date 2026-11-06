# Coaccess 专家权重页 Bank 布局：方案与 Qwen3/Qwen1.5 实验报告

日期：2026-10-13。本文依据当前工作区的脚本、结果 JSON、图表 provenance，以及对话“Qwen1.5-MoE coaccess Bank 布局优化”的实验交接整理。所有性能数字均为项目仿真结果，不是物理芯片测量，也不应称为官方 Sem-MoE/HiBand 实现的结果。

## 1. 先说明结论边界

- **已确认**：Qwen1.5-MoE 派生的 c4 memory-stress 负载中，coaccess 相对原始布局的五 cohort 配对平均端到端周期降低 **3.49%**；相对严格等改动页数的一个随机重排布局，增量仅 **0.250%**。五个 cohort 的两个比较均为正。
- **已确认**：Qwen3-30B soft70 的独立画像 repeat 3 → 留出 repeat 4 筛查中，画像重叠边仅覆盖留出边权重的 **1.79%**，coaccess 相对 heat 的固定轨迹同 Bank 重叠量**没有降低**，未通过预设筛查门槛。
- **不能推断**：Qwen1.5 的结果不能证明 coaccess 对所有 MoE 负载有效；Qwen3 的负面筛查也不能证明时间信息普遍无用。两个实验的“页”粒度和“时间关系”定义不同，百分比不可直接横向比较。
- **证据限制**：Qwen1.5 的 full-system 随机对照目前只有**一个固定随机布局**，在五个 cohort 上复用；低成本筛查中的 500 次置乱不是 500 次独立 full-system 仿真。Qwen3 repeat 3→4 只有一组独立配对，尚无等改动页数的 full-system 消融。

## 2. 优化问题与三种布局

先固定专家到 memory partition 的归属、路由请求、任务图、represented bytes、压力变换及非地址资源；只改变专家权重的 Bank 地址映射。Bank 布局要解决的不是“访问最多的页放哪里”这一单页问题，而是“可能同时访问的不同页是否被放入同一 Bank”。

| 布局 | 使用的画像信息 | 分配原则 | 当前局限 |
|---|---|---|---|
| Round-robin | 无 | 按确定顺序在同一 partition 的 16 个 Bank 间轮流分配 | 页数均匀不代表运行时负载或争用均匀 |
| Heat | 每页被读取/激活的频次 | 贪心均衡各 Bank 的累计单页热度 | 不知道两页是否在同一时段访问 |
| Coaccess | 单页热度 + 跨请求成对访问关系 | 在热度/容量约束下，惩罚有共访边的两页落入同一 Bank | 依赖画像关系能否迁移；当前为启发式，不是全局最优 |

这里的 **coaccess 是第三种**，但两种模型中的边权并不相同：

1. **Qwen3-30B**：逻辑页由 `(layer, expert)` 标识，每页为仿真中的 2,359,296 B 专家权重单元。读取 `events.csv` 中不同请求、同一 partition 的专家权重读取区间；若两个区间交叠，就把交叠时长加到对应边权。先按频次分配 heat，再用热度项加边惩罚项生成 coaccess；只对初始驻留页检查每 Bank 14 页的容量。代码见 [`derive_profile_assignments.py`](qwen3_30b_a3b_v3_6_experiment/expert_page_layout_audit/derive_profile_assignments.py) 和 [`build_graph_page_map.py`](qwen3_30b_a3b_v3_6_experiment/expert_page_layout_audit/build_graph_page_map.py)。
2. **Qwen1.5-MoE**：在冻结的 memory-stress 负载中，每个专家权重抽取 16 个 **4 KiB sampled pages**，Bank 由地址位 `address[17:14]` 解码。对同一 decoder layer、同一请求组内不同请求所激活的专家，按相同 slice 建共访边并累计出现次数；这是**波次级同时活跃代理**，不是逐笔 DRAM 请求或 Qwen3 的连续时间区间交叠。按每页的共访邻接权重排序，贪心选择已分配邻页边权最小、再兼顾热度的 Bank；每 partition 维持页数容量约束。代码见 [`screen_coaccess.py`](qwen_hiband_scope_fix/memory_bank_completion_v1/coaccess_qwen15_v1/screen_coaccess.py)。

因此报告中的“专家页”是各仿真定义的权重映射单元，不应不加限定地理解成操作系统分页，也不能把两模型的“改动页数”直接比较。

## 3. Qwen3-30B soft70：迁移筛查未通过

### 3.1 已做实验

先前 full-48 布局实验生成了 round-robin、heat、coaccess 的仿真结果和热点图；但不同布局会改变换页依赖图，三条原始周期不是完全同图的严格消融。早期 profile repeat 2 → eval repeat 1 的画像边加权覆盖率约为 1%–2%，且三个 eval 时间线只是同一批请求的反馈结果，不能计作三组独立留出样本。相关固定轨迹结果见 [`coaccess_validation_v2`](qwen3_30b_a3b_v3_6_experiment/results/coaccess_validation_v2)。

随后预先设定：画像边在留出集的加权覆盖率至少 10%，且 coaccess 相对 heat 在**同一固定时间轨迹**上降低同 Bank 重叠量，才进入下一独立配对和等改动页数对照。独立的 profile repeat 3 与 eval repeat 4 均通过 run manifest/validation 校验，但筛查结果如下：

| 指标 | repeat 3 → repeat 4 |
|---|---:|
| 画像/留出重叠边 | 373 / 347 |
| 匹配边 | 5 条 |
| 留出边权重覆盖率 | 1.794%（低于预设 10%） |
| coaccess 相对 heat 的改动页 | 263 |
| 留出边中触及改动页 | 8 条 |
| 同 Bank 状态实际翻转 | 0 条 |
| 留出固定轨迹同 Bank 重叠：heat / coaccess | 27,902,899 / 27,902,899 |

按预设规则，结果为 `NO_PROMOTION`。进一步诊断发现，263 个改动页中只有 45 个在留出运行被读取；留出读取落在改动页上的比例约 3.19%。画像和留出各自权重最高的前 20 条边互不重合。这些事实支持“当前画像关系没有有效作用到留出冲突边”的解释；尚不能分离请求分布变化、页粒度、启发式分配以及换页反馈的各自贡献。证据见 [`screen_pair34.json`](qwen3_30b_a3b_v3_6_experiment/results/coaccess_validation_v2/screen_pair34.json)、[`fixed_trace_pair34.json`](qwen3_30b_a3b_v3_6_experiment/results/coaccess_validation_v2/fixed_trace_pair34.json) 和 [`diagnosis_pair34.json`](qwen3_30b_a3b_v3_6_experiment/results/coaccess_validation_v2/diagnosis_pair34.json)。

### 3.2 如何解读早期 full-48 图

早期同一 soft70 cohort 的 coaccess 布局运行是 PASS，报告了 130,348,925 cycles；相应 pager-matched control 为 187,243,862 cycles，图注给出 30.39% 的差异。但该对照**不是**“coaccess 相对 heat 的纯时间信息增量”。同一轮 heat 布局原始周期为 128,481,704，round-robin 为 84,080,402；由于换页 DAG 随布局变化，这些数值只宜作为各方案实测结果，不能直接归因于 coaccess 边信息。已有图注也明确写到 coaccess 未胜过该 cohort 的 round-robin。来源：[`soft70 图注`](qwen3_30b_a3b_v3_6_experiment/results/expert_page_layout_v1/figures/soft70_phenomenon_cause_coaccess_layout_abc_v1_caption.txt)及各方案 `run_manifest.json`。

**阶段判断**：Qwen3 当前证据不支持把 coaccess 写成可迁移的性能优化。若继续研究，应先预注册请求相似性条件、验证边覆盖率和固定轨迹增量，再做等改动页数对照；不能直接追加昂贵的多种子 full-48 运行。

## 4. Qwen1.5-MoE：正向结果及其真正增量

### 4.1 负载与低成本筛查

实验对象是 **Qwen1.5-MoE-derived memory-stress workload**，不是自然服务负载或官方 Sem-MoE/HiBand 端到端实现。请求带 512-token prompt 上下文，当前 Bank stress 图使用的是 **128-token teacher-forced decode 路由**；24 个 MoE 层、top-4。正式对照限定为 c4 的 5 个冻结 eval routing cohorts。画像 20 个请求、留出 80 个请求，request ID 互斥，且筛查将五个 c4 留出组逐组与冻结图核对。现有 expert→partition placement 保持不变。来源：[`screening_summary.json`](qwen_hiband_scope_fix/memory_bank_completion_v1/coaccess_qwen15_v1/screening_summary.json) 及 [`screen_coaccess.py`](qwen_hiband_scope_fix/memory_bank_completion_v1/coaccess_qwen15_v1/screen_coaccess.py)。

在该**波次级代理**上，画像边对留出可变边的权重覆盖率为 100%；coaccess 的留出同 Bank 重叠量为 0，原始布局为 4,243,120，heat/round-robin 为 9,090,880。coaccess 相对 heat 改动 21,504 个 sampled pages。这个 0 **不代表真实 DRAM Bank 冲突为零**：full-system coaccess 仍有约 35.64% 的 Bank conflict rate。100% 覆盖率也只能说明该受控负载的可变边支持高度一致，不能外推到开放请求分布。

### 4.2 配对 full-system 结果

正式矩阵复用 5 个同配置 original PASS 运行，并新增 heat、coaccess、严格等改动随机重排各 5 个运行；15/15 个新增 case 均 PASS，统一使用冻结的 `build_contention4` 二进制，按 cohort 配对。heat 与 round-robin 在当前负载下得到**完全相同的 assignment**，不是两条独立基线。完整原始行、平均值及配对 bootstrap 统计见 [`full_matrix_summary.json`](qwen_hiband_scope_fix/memory_bank_completion_v1/coaccess_qwen15_v1/full_matrix_summary.json)。

| 布局 | 五 cohort 平均端到端周期 | 相对 original 的解释 |
|---|---:|---|
| Original Sem-MoE-inspired 地址布局 | 27,367,519 | 原始对照 |
| Heat = round-robin | 35,650,513 | 在本负载中退化，不能当作成熟优化基线 |
| 等改动随机重排（一个固定 seed） | 26,476,574 | 说明大规模重排本身已有收益 |
| Coaccess | **26,410,293** | 相对 original 平均配对收益 **3.49%** |

coaccess 相对 original 的五个配对收益均为正，范围 **3.13%–4.58%**，五 cohort bootstrap 95% 区间 **3.18%–4.04%**。但相对**严格等改动随机布局**的端到端增量只有 **0.250%**，五 cohort 范围 **0.099%–0.394%**，bootstrap 95% 区间 **0.136%–0.364%**。这些区间只量化当前五个固定 cohort 的重复抽样不确定性，不覆盖新模型、新路由分布或随机布局 seed 的变化。

机制指标方向一致：coaccess 相对 original 的平均 Bank conflict rate 从约 78.38% 降至 35.64%；相对等改动随机布局则从约 42.59% 降至 35.64%。但机制指标下降幅度不能作为端到端加速比；从仿真周期看，coaccess 特有的增量明显小于相对 original 的总收益。一个合理解释是地址重排本身贡献了大部分周期收益，**这是根据单个随机布局的对照作出的有限推断**，还需要多随机布局和更广负载验证。

### 4.3 统一色标热点图

已有三联图比较 original、等改动随机、coaccess，三者使用同一绝对 `magma` 色标。矩阵为 **16 decoded Banks × 24 decoder layers**；数值是跨请求同 Bank 首次 issue 前等待 ticks，在 16 partitions 上求和，再对五个 c4 eval cohorts 取均值。三个面板的总等待分别为 **330.87M、110.57M、88.30M ticks**；coaccess 相对 original 下降 73.31%，相对随机下降 20.14%。共享色标上限是合并正值单元格的第 99 百分位，饱和颜色不删除原始数值。该图显示等待热点的变化，**不能单独证明 73.31% 的端到端加速**；相应配对周期收益仍应报告 3.49% 和 0.250%。见 [`统一色标图 PDF`](qwen_hiband_scope_fix/memory_bank_completion_v1/coaccess_qwen15_v1/coaccess_bank_hotspot_unified.pdf) 与 [`heatmap_manifest.json`](qwen_hiband_scope_fix/memory_bank_completion_v1/coaccess_qwen15_v1/heatmap_manifest.json)。

## 5. 横向比较、风险与下一步

| 对比维度 | Qwen3-30B soft70 | Qwen1.5-MoE memory-stress |
|---|---|---|
| 权重映射单元 | 每 `(layer, expert)` 一个 2.25 MiB 逻辑页 | 每专家 16 个 4 KiB sampled pages |
| coaccess 边 | 不同请求读取事件的**实际区间交叠时长** | 同层、同请求组的跨请求活跃专家**波次级共现次数** |
| 留出覆盖 | repeat 3→4 边权覆盖 1.79% | 受控 c4 负载的可变边支持覆盖 100% |
| 最小筛查 | 相对 heat 无固定轨迹收益 | 相对 heat 代理重叠量降至 0 |
| 完整系统证据 | 旧 full-48 原始周期受换页 DAG 差异影响；新独立配对未升级 | 五 cohort 配对仿真：相对 original +3.49%，相对一个等改动随机布局 +0.250% |

**已确认的研究结论**不是“coaccess 总是有效”，而是：在 Qwen1.5 当前结构化、波次同步的内存压力负载里，画像关系可以迁移并带来小幅的随机对照之上增量；在 Qwen3 当前独立请求配对中，边关系迁移不足，未显示增量。是否由模型架构、请求构造、页粒度、重叠定义或布局算法主导，**暂时无法区分**。

建议下一步按成本从低到高推进：

1. 对 Qwen1.5 固定五个 eval cohorts，生成多个**独立**且严格等改动/等容量的随机布局，报告 coaccess 对随机布局分布而非单 seed 的增量；低成本代理与 full-system 分开统计。
2. 对 Qwen1.5 增加不依赖“同波次同步”假设的请求时序/路由条件，检查 100% 边支持覆盖和 0 代理重叠是否仍成立；不要把现有负载的结构性质直接称为普适迁移。
3. 对 Qwen3 先做预注册的同分布画像—留出配对与活跃页限定消融；若边覆盖仍低，停止 full-system 扩展。
4. 所有新运行写入隔离目录，保留已有 PASS 和失败日志；图中保持原始值、随机对照和 coaccess 的统一色标，并同时给出端到端周期。

## 周报版摘要

完成 Qwen3-30B 与 Qwen1.5-MoE 的 coaccess Bank 布局证据整理。Qwen3 独立 repeat 3→4 配对仅 1.79% 的留出边权覆盖，相对 heat 无固定轨迹增量，未进入多种子 full-48。Qwen1.5 的 c4 五 cohort 统一二进制配对仿真全部 PASS，coaccess 相对原始布局平均降低 3.49% 周期，但相对一个等改动随机布局仅降低 0.250%；统一色标热点图已生成。当前最重要的后续验证是 Qwen1.5 多随机布局与非同步请求条件，以分离 coaccess 信息收益和一般 Bank 重排收益。

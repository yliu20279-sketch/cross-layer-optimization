# LingBot TI2V 基线准备

状态 PARTIAL。基础 LingBot-Video-MoE-30B-A3B，refiner 关闭，混合 BF16/FP32。开发采用既有 example_4 的真实路由和双 CFG，保留分支、专家槽位、权重及共享专家。独立留出待冻结，禁止复用已见样例。目标 16 NPU/16×512 MiB HB、host128 GiB、目标 GPU 0。到达合同暂限单请求，未采纳并发到达假设。

数值参考绑定步骤3原 GPU fixture 及采集冻结清单。SOURCES.json 记录本地证据文件的哈希，底层权重、输入和远端全量数组须依冻结清单逐项核对后才能签署正式基线。当前最强已验收层内证据为 v6 双轮 TP 检查点拼接，保留 v5 EP 回执，准入仅 PASS_LIMITED。v11 连续 TP/EP 暂列候选，需最终退出、独立数值/DAG/SRAM/反馈及归档回执。未冻结端到端性能 B。

## 依赖及验收账本

| 链路 | 必须保留的依赖 | 小样本验收 |
|---|---|---|
| 条件编码 | 请求/图文预处理→文本条件、图像条件及初始 latent→两 CFG 分支 | 分别核对条件张量与初始 latent 的来源、dtype、shape 和哈希 |
| DiT 层内 | norm→Q/K/V→attention→顺序 FP32 O 累加→残差→router→EP dispatch→专家/共享专家→按槽位返回→层输出 | 复用双 CFG 各64查询、完整 KV 上下文开发门，逐位核对边界、路由及层输出，不能将截取样本当整层 |
| 去噪跨步 | 双分支输出→CFG合并→调度器→下一步 latent | 核对分支/层/步绑定、调度器状态及最终 latent，旧 GPU latent 回执只用于参考 |
| 视频 | 最终 latent→VAE decode→后处理→帧序列 | 核对解码输入、原始帧 shape/dtype/顺序与参考，另记编码/输出时间 |

事件须含 request_id、event_id、step/layer/cfg/rank、op、shape/dtype、依赖 ID、资源、读写及传输字节、开始/完成、时钟域与时间换算。将资源串行、同步、缓存写回/回执和迁移前置加入实际依赖；分别核算 CPU、PCIe、HB/SRAM、NoC、缓存维护和迁移。按请求到达至帧完成的实际依赖求关键路径，重叠区间取并集，禁止直接相加阶段时长。缺事件或时钟换算记未测，不能填零。

Sem-MoE 需有真实专家 owner、dispatch/return 和映射生效记录。HiBand 需有实际层次拓扑、带宽/路由路径和生效回执，并对照容量与传输守恒。目前真实路由与 TP/EP 证据只支持开展适用性验证，两策略联合生效待证。完整成本及视频边界通过后才可冻结正式 B；全套优化准入前暂停正式矩阵和 CA 单独对照。

## 本地复核

在项目根目录执行 PowerShell：

    Get-Content lingbot_ti2v_baseline_20261103_v1/SOURCES.json -Raw | ConvertFrom-Json | ForEach-Object { if ((Get-FileHash -LiteralPath $_.path).Hash -ne $_.sha256) { throw "SHA256 mismatch: $($_.path)" }; $_.path }

该命令验证证据索引；目标运行复跑命令及 D 盘归档仍待完成。

## 两份拆分咨询补记（2026-11-03）

**应用图**　正负文本与首帧/VLM条件、首帧VAE encode、latent初始化；随后40个去噪步，每步两条CFG分支各执行48层，汇合后依次执行scheduler更新及inpainting，再释放下一步；最终VAE decode与帧输出单列。保留step、timestep、CFG身份、视觉token的(t,h,w)、文本/视觉掩码和CP padding。逐边界冻结张量身份、shape、dtype和SHA，先过单层，再过跨步latent和视频边界。

**层内图**　timestep modulation→RMSNorm→Q/K/V投影→Q/K Norm→3D RoPE→非因果Attention→O投影→残差→MoE Norm。路由单列FP32 GEMM、sigmoid、correction bias、4组选2组、Top8、从未加偏置分数取权重、归一化与2.5缩放、padding后有效权重。记录原始分数、选择分数、有效权重、token owner和inverse permutation。专家拆为pack/dispatch、gate/up、SiLU×up、down、return和slot恢复。按源序执行FP32加权累加，保留O跨rank累加顺序；shared expert独立，最终残差等待两支完成。逐阶段比较，首差停止。

**通信与释放**　源Ulysses CP分别记录Q/K/V三次sequence→head和Attention后一次head→sequence all-to-all；双rank CFG另计latent及unconditional输出广播。目标TP16和EP16按独立通信类别记账；EP16等容量每rank 8个专家属于目标映射，源路径为本地GroupedExperts。每个有效assignment仅dispatch一次，显式等待权重与激活到齐；NoC末包和DRAM末回调后才解锁消费者，按最后读者释放。PP若引入须另计每步fill/drain与跨步回边。

**回执等级**　v5 EP每轮98,869行、7,680次逻辑远端传输及96,880条水平PopNet；v6 TP每轮46,380条逻辑消息及208,590条水平PopNet，均保留检查点拼接范围。维护索引转述11月3日10:23专责观察，v11首轮16 rank通过并完成307,870条NoC回放，第二轮无条件N00到11,520/48,986。本地未见更新的最终回执，113只读SSH被拒绝；当前仍待第二轮退出、独立数值/DAG/SRAM/反馈审计及归档。宏计算代理仍缺完整CPU/PCIe与逐MAC成本。

**策略边界**　咨询提出的RR/Sem-MoE与固定/动态HiBand四组配对保留为未来方案。先验收策略实际生效并守恒同一输入、路由、精度、拓扑、容量及缓存初态；Sem-MoE画像与评估按完整视频隔离。正式PK等全套优化合入并准入。

来源：[咨询一](../lingbot_operator_graph_v3_6_20261027_v1/consultation_sem_moe_sota_1.md) · [咨询二](../lingbot_operator_graph_v3_6_20261027_v1/consultation_sem_moe_sota_2.md) · [采集](../lingbot_step3_capture_20261028_v1/REPORT.md) · [EP](../lingbot_step5_full_ep_20261031_v5/COMPLETION_20261101.md) · [TP](../lingbot_step5_full_tp_20261101_v6/COMPLETION_20261102.md) · [v11协议](../lingbot_step5_continuous_20261102_v11/README.md) · [维护索引](../project_maintenance/CONVERSATIONS.md)

## 2026-11-05 步骤3收尾

双CFG K小路径的一键封装入口已在113新隔离目录实际重跑。cond/uncond各自两遍独立NoC反馈、数值与完成门控有限通过，238载荷本地SHA通过。见[收尾报告](../lingbot_step3_closeout_20261105_v3/REPORT.md)、[最终回执](../lingbot_step3_closeout_20261105_v3/CLOSEOUT_AUDIT.json)。原计划下一步为步骤4的CFG合并、scheduler及VAE边界。完整单层成本仍PARTIAL。

# LingBot TI2V 基线实现与算子拆分计划

日期 2026-11-03。目标为 LingBot-Video-MoE-30B-A3B 基础 TI2V，关闭 refiner，混合 BF16/FP32，16 NPU、16×512 MiB HB、host128 GiB、目标 GPU 0。example_4 用于开发，独立留出按完整视频在调参前另行冻结。当前计划仅覆盖基线准备和有界验证。

## 1. 绑定基线和参考

- 从同级 lingbot_v11_baseline_freeze_20261103 读取 BASELINE_FREEZE.json、COMPLETE_REVIEW_DELIVERY.json 和已核验的审阅包。记录 v11 两轮连续单层 PASS_LIMITED；v5/v6 保留为检查点子图对照。497 个包载荷已本地验 SHA，1,127 项远端原始文件按索引用于选择性复核。
- 将源码修订、构建二进制、配置、权重切片、双 CFG 输入及阶段参考逐项绑定 SHA-256。记录视频、step、timestep、layer、CFG、真实 token 坐标、rank、专家槽位、dtype、shape 和到达时刻。先固定单请求，正式 B 另行冻结到达与缓存初态。
- 原 GPU fixture 作为数值参考；记录每个边界的参考注入。FP32 软件累加器参考与原 GPU BF16 参考分开。所有新增实验使用独立目录并保存失败现场。

## 2. 拆分算子与依赖

- 应用层。正负文本与首帧/VLM 条件编码、VAE encode、latent 初始化；40 步各执行两条 48 层 CFG 分支；两支汇合后 CFG combine、scheduler 更新与 inpainting；最终 VAE decode 和帧输出。
- Attention。timestep modulation、RMSNorm、Q/K/V 投影、Q/K Norm、3D RoPE、非因果 score/softmax/value、O 及残差。源 Ulysses 的 Q/K/V sequence→head 与输出 head→sequence 分开记录；目标 TP 记录实际切分与跨 rank 的顺序 FP32 O 累加。CFG 广播另记。
- MoE。norm、FP32 router GEMM、sigmoid、correction bias、4 组选 2 组、Top8、从未加偏置分数取权重、归一化和缩放、padding 掩码及有效权重。随后 pack、EP dispatch、gate/up、SiLU×up、down、return、按源槽位恢复并加权累加。共享专家独立执行，两支完成才释放 join 和残差。每个有效 assignment 只发一次。
- 物理层。分别记录 CPU、DMA、HB/DRAM、SRAM、NoC、计算及回调。绑定字节、地址、所有权、最后读者和释放。权重读回与激活到达都满足才可发射专家计算。记录时间域、原始 tick、换算、开始、完成和依赖 ID。

## 3. 实现并执行双 CFG 有界成本探针

1. 用 v9 CPU 服务和 v11 真实输入索引，在隔离目录建立 cond/query0 和 uncond/query0 的独立输入清单。各自选择一条确有 host/HB 读写及远端通信的路径。缺少无条件权重切片或参考时按相同源码语义生成并核验来源。v9 的两轮反馈都使用同一条件输入，不计为双 CFG。
2. 复用真实 Sniper CPU/FDA16 回调及 HB/DRAM 事务。将 CPU 返回载荷和完成时刻写入带请求、分支、版本和事务 ID 的回执。接入 V3.6 PCIe DMA 模型的分段、方向、队列、IOMMU、固定延迟和实际轮询完成事件，记录具体配置。FIFO 传完只提供传输证据。
3. 在同一条路径触发脏行写回。将写回 token 与最后一条 DRAM 回调配对，核对地址、字节及新版本，再允许相关 DMA/消费者读取。用 PopNet 接收端末包完成事件释放通信依赖，单列注入时间。回放反馈若参与计时，记录应用位置及对应消息身份。
4. 将 CPU 2.5GHz、DRAM 1.25ns 和网络、DMA 的原始时间按配置换算到统一时钟，按约定向上取整。消费者释放需同时具备四类同身份完成回执，并满足 start ≥ max(CPU 返回、DMA 完成、写回回调、NoC 末包)。保留各服务区间、资源排队、重叠及关键路径。重复、过期、跨 CFG、缺失或提早回执须拒绝。分别延迟四种回执验证各自能推迟释放。
5. cond/uncond 各跑一条真实路径，固定并记录运行上限、可执行命令、输入清单和子进程退出码。首差停止并保留日志。逐位比较约定的 FP32 软件参考及 BF16 Golden，核对 payload SHA、地址和有效字节，再用独立脚本重放原始事件检查完成顺序。部分覆盖按 PASS_LIMITED 报告，未测成本留空。

## 4. 后续准入

成本探针通过后，依次验证一次 CFG 合并和 scheduler 的下一步 latent、冻结最终 latent 的 VAE 解码、连接目标执行链。再验收 Sem-MoE 专家放置和 HiBand 配置实际生效及完整成本，冻结正式 B。全套优化准入前暂缓正式 PK 与 CA 消融。

## 依据

- 113 同级目录 lingbot_v11_baseline_freeze_20261103/BASELINE_FREEZE.json
- 113 同级目录 lingbot_step5_continuous_20261102_v11 的 PROTOCOL.json、STATUS.json 和四类独立审计
- 项目 lingbot_step5_cpu_service_20261101_v9 的 actor.py、gateway.cpp 和 REPORT.md
- 项目 whisper_operator_inventory/target_architecture_v3_6/pcie_dma_model.json
- 项目 lingbot_operator_graph_v3_6_20261027_v1 的两份 consultation_sem_moe_sota 文档

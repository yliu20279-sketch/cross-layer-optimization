# 完整TP attention/O续作（2026-11-01）

当前RUNNING，步骤5仍PARTIAL。目标同一已见layer0/step0双CFG全部98869个查询、完整49883/48986 K/V上下文；16 NPU运行时/16×512MiB外部HB服务，保留BF16/FP32、host128/HB8、目标GPU0。

新计算：全部查询的Q、每head norm/RoPE、完整非因果attention core、rank0至15原FDA16 FP32 O累加器传递、rank15只加一次bias、BF16输出真实传给origin，再产生FFN输入。完整K/V投影仍复用步骤4已验收的自主CPU结果，不把它写成重新执行K/V GEMM。

完整MoE已通过，不重复其8小时实验。新生成的完整FFN输入必须逐位等于已验收MoE的输入，且旧输入/输出文件SHA与冻结JOIN_BINDING一致，才可消费旧实际原生MoE结果继续计算层输出；新层输出仍对原GPU逐位核对。旧MoE边界另行验证，不能把两个检查点拼接称为同一次连续统一全层时序或把旧MoE成本当零。

每rank1计算线程、nice10、两轮反馈、24小时生产上限、30分钟独立数值审计上限。首个attention/FFN输入/层输出差异或异常/超时停止保留；独立watch_core每10秒对已提交core前缀核原GPU值，首差保存实际/参考并仅停止经PID/命令行核验的本任务进程组。该观察器只读，不修改数学程序或门槛。

本次快照：第一轮cond全部16个head均已独立核对前4416个查询，9043968个core BF16值的FP32容器元素零差异。它只是当前前缀，不是全量通过。精确实时状态在113的PROGRESS.json、case*/N*/PROGRESS.json及LIVE_CORE_AUDIT_PROGRESS.json。

supervise、独立数值/DAG/Bank/反馈审计和补齐关键审计/大数组SHA的complete_collect均在113后台，不依赖本机连接。原始数值数组/大DAG/日志留113，最终compact包有原始载荷SHA索引。SOURCE包20256B，SHA fab24d103cac772219a70d9fb5bb2d43300a78a8568be4675f0134f18f16f144。

未认证：新K/V目标GEMM、完整CPU/host/PCIe/软件特殊函数和缓存/每算子每MAC SRAM成本、连续TP+EP统一虚拟时间与pager状态、HiBand/Sem-MoE净收益。实际SRAM仅DMA暂存，端口/条带仍是明确研究配置。原未通过O独立部分和130/106差异及其他历史失败保留。

来源：PROTOCOL.json、FREEZE.json、prepare/worker/audit源码、LIVE_CORE_AUDIT_SNAPSHOT.json；MoE最终回执和本地核验见../lingbot_step5_full_ep_20261031_v5/COMPLETION_20261101.md。


2026-11-01续查：运行5707.60秒，第一轮条件分支16头各24704行，独立core观察50593792个BF16元素零差异；尚无完整rank结束，不能认定全层通过。CPU成本及回调有限验收另见v8/v9报告。


2026-11-02检查：第一轮16 rank及208590 NoC完成；第二轮仍运行，最终两轮独立验收未生成，见CHECK_20261102.md。旧6—8小时估计偏乐观。


2026-11-02最终：完整TP两轮及四类独立审计有限通过，335载荷本地SHA通过，详见COMPLETION_20261102.md。旧运行中快照已过时，步骤5仍PARTIAL。

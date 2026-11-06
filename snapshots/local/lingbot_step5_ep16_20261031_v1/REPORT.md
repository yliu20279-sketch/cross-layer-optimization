# LingBot步骤5：EP16固定通信与TP16数值门

当前PARTIAL，步骤5尚未全部完成。原混合BF16/FP32、host128GiB/HB8GiB、目标GPU0保持；不下载refiner，无外部GPU或完整模型重跑。

已实际完成：

- 同一已见layer0/step0双CFG98869行，自主路由790952次专家分配。origin=t mod16、owner=e mod16；实际4112B记录（16B身份/权重元数据+4096B BF16向量）序列化、重载并按原槽位还原。共享专家每token只取一次。复用步骤4自主完整批量专家输出，没有新执行专家算术。
- cond399064分配（本地24929/远端374135），uncond391888（本地24527/远端367361）。含本地CPU序列化在内往返共6504789248B，不等于全是NoC流量。FFN共202483712个BF16元素与原Golden逐位一致。
- 预定每分支前32视频+末32条件查询，1940条真实字节远端dispatch/return经实际PopNet/规范4x4+gateway拓扑回放；没有缩小包字节。全查询NoC未运行，回放为open-loop，尚未接入完整计算/通信完成驱动DAG。
- 独立审计12242项通过：完整1619869696个槽位BF16元素与步骤4一致，原Golden文件SHA、独立Torch还原FFN、身份/路由计数/1940条NoC记录及flit守恒通过。重复return、错误owner、权重位损坏、缺返回提前combine四项负对照通过。

发现并保留未通过候选：Attention-TP16 O投影独立分片FP32求和在双CFG各131072个输出中有130/106个BF16差异，原映射不能直接晋级。串行传递原FDA16累加器、rank0至15按连续K128顺序更新、末rank只加一次原bias后回BF16，FP32累加器及最终BF16均零差异。该项是同原GPU core输入的O投影CPU诊断，不是自主完整TP16 attention或NoC执行。新候选映射见MAPPING_AMENDMENT.json，原MAPPING不改。

静态分阶段容量方案：每rank最大HB246825216B（限536870912B），SRAM1853440B（限4194304B）。要求attention/MoE生命周期分离、owner输入64行背压、原全批量M先选数值recipe再分行处理，其他模块及未活动权重留host。它不是实际pager、SRAM Bank、host/PCIe运行验收；数学域表继续占用既定host预算。

剩余完成门：

1. 将TP16逐head attention与O累加器传递接回完整自主层，不能套普通all-reduce通信量。
2. 把EP16实际payload、专家计算、共享分支及restore接入由真实网络完成释放的统一DAG；目前CPU序列化与NoC回放是分开的。
3. 实际host128后备→PCIe/gateway→HB install→SRAM及8 Bank生命周期与32B事务验收，保留所有非原生数学软件服务成本。
4. 再扩大完整查询/层范围并独立审计；未完成前不报告目标总时延或HiBand/Sem-MoE收益。

交付：review.tar.gz为36载荷compact复核包，487821B，SHA e875de7fa34a6ca3d36b216ec3dd0dcb3b109b5c339d59cfc6ab08f347dc5e95；外包及全成员本地SHA通过。大型完整返回槽位及O候选数组留113；不是全量回传。POSIX其他用户可读/目录可遍历检查通过，未跨账号登录实测。启动命令首次引号错误未启动实验；后续无数值停止，O部分和失败保留。

原始来源：review/FUNCTIONAL_RESULT.json、INDEPENDENT_AUDIT.json、POP_NET_RESULT.json、TP16_O_RESULT.json、CAPACITY_PLAN.json、FINAL_MANIFEST.json及本地LOCAL_VERIFICATION.json。远端目录/mnt/sda1/h3240101068/lingbot_step5_ep16_20261031_v1。

# LingBot步骤5：16节点连通层两轮验收与完整MoE续作

步骤5整体仍PARTIAL。本轮已完成双CFG各64个预定查询、完整49883/48986 K/V上下文的16节点连通层两轮验收；完整98869行MoE/EP16子图通过准入后已在113独立后台运行，尚未完成。

## 已通过的连通层

16个独立NPUSim actor、16个512MiB外部Ramulator服务、规范4x4+gateway PopNet拓扑。每rank自主计算一个head的选定Q、QK归一化/RoPE和全上下文attention，按rank0至15传递原FDA16 FP32 O累加器，末rank只加一次原BF16 bias再回BF16。完整K/V投影是步骤4已验收的自主CPU结果，重新执行每head归一化/RoPE；本次没有重跑全查询K/V GEMM或全模型。

attention结果分发至token origin；重新计算FFN输入、自由router与共享专家；源完整专家批量M由步骤4自主全FFN/路由绑定提供，owner收齐该专家选定真实输入后重新计算，再按真实网络完成回执返回origin。不是复用步骤4专家输出。原Top8槽位、FP32四路归约和BF16边界保持。

- 两轮每轮双CFG128行，5个边界共1310720个BF16元素对原GPU Golden逐位一致。主独立审计22055项通过，另有attention独立审计524288元素零差异（跨两轮）。
- 每轮1582次逻辑传输、24688960B实际载荷、1792条水平PopNet；第二轮1792条全部实际使用第一轮反馈，不是只重复无反馈回放。
- 每轮显式原生宏事件DAG为5774节点/7340边，无环，所有发送/接收SHA与字节匹配，接收完成不早于发送完成。每轮4项审计负对照通过。
- 每轮231041条域服务记录顺序核对通过；DRAM服务配置1.25ns。未做物理时序校准或完整CPU/DRAM逐值独立计时认证。
- 实际4MiB SRAM字节数组，64KiB分块暂存；每Bank共享读写端口、32B条带为显式研究配置，不是已确认的原规范端口模型。每轮暂存读写各2967412736B、Bank服务23184664周期；两轮160项独立字节/分块/周期/峰值检查通过。三种冲突挑战2/1/3周期及越界拒绝通过。此处只覆盖HB DMA暂存及读回，不覆盖每MAC、SFU和完整算子Bank访问。
- 统一入口66条子进程退出记录全部0，控制器退出0，约1270.60秒完成两轮。该host墙钟不是目标时延。

CPU载荷数学仍是软件求值＋原生事件门控、通用向量代理。初始CPU权重/激活供给、完整host/PCIe/gateway成本及全部算子原语成本不在本次通过范围。详见COVERAGE_AND_COST_GAPS.json，缺失成本不能当零。

## 本地独立交付

最终归档50163466B、739载荷，SHA256 9b5d400ad5641647e5f6be6fba9e725cdd676a03939395c5d7fd4b4c49365de6。外包及全部成员本地SHA通过，保留两轮全部小数值数组、实际DRAM事务CSV、显式DAG和两轮域服务/水平反馈CSV；原始进程控制日志仍留113 run目录，未声称全部大日志回传。

本地独立NumPy核对194对数组，每轮5767168个FP32容器元素（含O累加器），两轮有限值且逐位一致，无FP16/FP64容器。这是同一个已见输入的反馈重跑，不是两个独立样本或未见留出。

## 保留的停止与修复

v2部分rank导入时并发编译步骤4共享派生.so，出现file too short；其他rank已发生HB活动，该统一尝试失败，未把它算成全部未执行。v3将数学库改为独立编译一次、worker只读加载；随后因逐origin重复搬权重成本较高主动停止，现场及原因保留。v4改为owner批量计算并接入实际SRAM暂存后完成两轮。

旧共享派生库和新隔离库最终SHA均为0ddea8f4e2f86590fd393ee64933b2f3b7591f8b3d935db84c47982d94931b3c；步骤4原数值输出、旧失败和审计回执未改。当前库48元素快慢路径回归通过。审计源码仅修正过时的无SRAM描述并限4 CPU线程；数值条件不变，原源码/冻结索引和AUDIT_AMENDMENT.json保留。

## 已自动启动的下一门

完整MoE目录：../lingbot_step5_full_ep_20261031_v5/。只在本轮数值/DAG、SRAM和全部反馈三项独立门通过后才启动；当前已确认构建及源码冻结校验通过，16个actor进程nice10正常运行。

范围是同层同step双CFG全部98869个FFN输入：来自步骤4自主全FFN结果并核SHA，自由router重算，所有真实专家/共享专家重新计算，真实dispatch/return、HB和SRAM暂存、两轮反馈，原Golden仅作输出核对。它不包含完整查询的TP attention；不能将MoE子图通过称为完整DiT层原生通过。

每rank1 CPU线程（16计算线程）、nice10、最长12小时；异常/首差/超时即停，不放宽门槛、不自动重试。wait_launch/supervise/post_collect、独立SRAM及反馈审计和final_package均在113后台，不依赖本机持续开机。启动器沿用RUNNING_UNIFIED_SELECTED状态字符串，但实际数据规模由该目录PROTOCOL和全索引决定，不能把该旧字符串误读为只跑64行。

本轮无新增GPU参考、完整模型或物理NPU运行；原混合BF16/FP32、host128/HB8、目标GPU0不变。尚无HiBand/Sem-MoE/Bank策略收益结论。还需完整MoE最终回执、全查询TP attention以及完整CPU/host/PCIe/算子/SRAM成本后，才能判断步骤5的完整准入。

来源：review/INDEPENDENT_AUDIT.json、ATTENTION_INDEPENDENT_AUDIT.json、DAG_AUDIT.json、SRAM_INDEPENDENT_AUDIT.json、FEEDBACK_AUDIT.json、RUN_EXIT.json、各case原数值/事件/事务文件，LOCAL_VERIFICATION.json和LOCAL_NUMERIC_AUDIT.json。

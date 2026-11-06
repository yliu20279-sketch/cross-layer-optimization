# swe_qwen3：单token SiLU×up、down与结果返回

日期：2026-10-28。片段状态PASS_LIMITED_M1_EXPERT49_TAIL_AND_RETURN；步骤3整体仍PARTIAL。

固定专家49、row0/slot0、owner1→origin0。SiLU、乘法、down及返回源节点后的BF16字节全部与CPU原源码逐位一致；不放宽容差。不是完整MoE、原GPU数值或物理性能认证。

## 精度与CPU预检

沿用原BF16模型和128 GiB host＋8 GiB HB研究overlay，原host8规范不改。严格保留gate BF16→SiLU BF16→与up BF16相乘→乘积BF16→down BF16边界，没有把未舍入FP32 gate或乘积直接喂给下游。

SiLU采用host NumPy FP32表达式x/(1+exp(-x))，经原codec回BF16。当前安装环境的全部65280种有限BF16输入与CPU原F.silu逐位一致，另有真实gate768项一致；不覆盖NaN/Inf，也不把特定库实测外推其他exp实现。[SiLU预检](cpu_attempt1/SILU_CHECK.json)。它是显式host软件回退，不是NPU exp/SiLU内核或目标CPU时序认证。

在既有180次独立M1专家调用上，逐阶段检查SiLU138240项、乘积138240项、down368640项，全部BF16逐位一致。[CPU尾链](cpu_tail_attempt1/RESULTS.json)。down沿用固定源AVX2 GEMV的64lane FP32树，本轮K=768，输出2048；没有单输出修正、FP16/W4替换或FP64目标计算。M>1 batch每投影21处既有差异和softmax FP32差异继续保留。

## 实际目标片段

从[上一阶段](../swe_qwen3_gate_reduction_20261028_v1/REPORT.md)已认证gate/up的BF16导出及完成边界13660642 ns起步。新上下文显式H2D恢复这两个BF16输入，绑定同一专家down原BF16权重的只读host文件offset、SHA及owner1 HB区间。并非原执行器跨进程连续保持状态；上一阶段codec/export成本仍未认证，不能因边界恢复而补称完整时序。

1. gate真实HB读取、D2H、host SiLU、BF16 H2D提交。
2. SiLU/up分别真实HB读取及host精确解码，临时FP32 H2D后在原生向量乘法回调执行逐元素乘法；FP32结果写HB，再显式D2H、BF16编码、H2D，形成down的真实BF16中间输入。
3. down原权重先BF16 H2D驻留、HB读回/D2H、host精确展开、FP32工作区H2D；乘积BF16亦经真实读回解码。执行完整1×768→2048的64lane原生乘加树，回写FP32 HB，随后D2H/BF16编码/H2D。
4. owner1读取真实BF16结果，创建独立TX快照，显式SRAM drain后通过原生NoC返回origin0。128 B头保留原32 B描述符中的row/slot/expert/owner/origin/weight bits/epoch，加4096 B专家输出，共4224 B、33个128 B包。
5. 全部尾包完成后才允许数值RX复制；源TX固定到尾包，RX暂存固定到origin0 HB提交，最后读取返回inbox。4096 B body与完整CPU原专家结果逐字节一致，inbox仍等待source_weighted_commit，不执行路由加权或跨专家合并。

阶段结果：SiLU768项、乘积768项、down2048项、返回body2048项，均0差异。[状态](native_attempt1/STATUS.json)、[结果返回依赖](native_attempt1/RETURN_DEPENDENCIES.json)、[returned_frame](native_attempt1/returned_frame.bin)。

## last-reader与门控

每个中间HB区间登记计划读取者，读取完成前禁止退休。gate保留至host SiLU读取，SiLU/up保留至host解码；临时FP32输入保留至乘法完成；乘积各精度工作区分别保留到编码或down输入解码。down输入及权重各有32个输出tile读取者，全部完成后才可退休。每个SRAM tile的算术读取者计数完成前禁止释放。

down输出保留到编码/返回TX快照完成，之后TX单独固定至NoC尾包；目标RX固定至HB提交。origin0返回inbox保留给未来加权commit。退休为回收资格，不代表本轮已覆盖每个地址或产生额外换出流量。记录中done_ns对跨host解码阶段是保守持有界，未宣称最早可复用的精确CPU时间。[LAST_READERS](native_attempt1/LAST_READERS.json)、[RESIDENCY](native_attempt1/RESIDENCY.json)。29项未驻留、提前退休、SRAM早释放、缺包/重包/早尾包、RX提前释放及提前消费负对照通过。

## 独立审计与资源

[远端审计](native_attempt1/INDEPENDENT_AUDIT.json)重算真实分片/tensor SHA，用完整CPU原专家gate→up→SiLU→乘法→down对照；另外用标量libm表达式复核SiLU，以独立NumPy FP32树和整数RNE复核down。执行库/NoC桥接SHA、依赖事件、32 B事务、主机窗口、全部读取者与释放顺序重新核对。[本地因果审计](LOCAL_CAUSALITY_AUDIT.json)只核回收账本，不声称本地读取远端权重。

两节点合计108573个原生事件、594984个32 B DRAM事务、3406592个向量op；SRAM单节点峰值3145728 B。父阶段保守叠加本轮HB分配共32333376 B，单CH范围未超512 MiB，总量未超8 GiB。host沿用完整后备61064245248 B＋17 GiB运行/IO预留，小型解码工作区位于IO预算内。

返回NoC输入峰值4 flit、输出1 flit、NI阻塞0，逐周期容量检查启用。0阻塞只描述这次单消息，不说明多专家拥塞收益。send_ready18054468 ns、尾包18054605 ns、目标HB提交18055532 ns、消费读取完成18056176 ns；这是显式服务代理时刻，不能作完整系统时延或加速比。

NoC仍为“原生尾包证书后数值复制”，内部flit不携带本负载BF16字节，非逐flit数值认证。host SiLU、codec、control/header/gateway成本均未完成目标时序认证，SRAM聚合服务不代表逐Bank仲裁。无源GPU专家中间值认证、无新GPU/agent/SWE/Sniper/新留出；本轮新增原生片段1，本线累计9，Sniper累计3、物理NPU0。

代码与协议在运行前冻结，失败和历史目录不覆盖。交付全部成员SHA以[DELIVERY](DELIVERY.json)、[本地验包回执](LOCAL_DELIVERY_VERIFICATION.json)为准。

## 下一步

为同一token补其余Top8专家结果及源顺序commit：保留BF16路由权重乘法与逐次index_add边界，不能按到达顺序累加。本轮仅专家49/slot0返回，不代表其他7个slot已计算。batch内核归约合同继续独立修复，softmax FP32差异仍FAILED_RETAINED。功能推进不等待SWE修复成功率。

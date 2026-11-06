# swe_qwen3：同token Top8计算、返回与BF16源序commit

日期：2026-10-28。状态PASS_LIMITED_FIXED_TOKEN_TOP8_RECORDED_DISPATCH；步骤3整体仍PARTIAL。

本轮补齐固定R0002第0层row0 token的其余7个专家，复用此前专家49的认证返回，完成8份BF16路由加权和8个源序合并前缀。51项阶段检查均逐位一致，334项负对照通过。最终2048元素BF16状态已在origin0 HB提交，仍保留downstream_residual读取者。

这是“已记录dispatch＋M=1专家”的条件功能验证，不是自主router、完整prefill batch、完整层、模型或策略收益PASS。

## 输入、源顺序和精度

沿用原BF16、128 GiB host＋8 GiB HB显式研究overlay；原host8规范不改。固定真实activation、已认证metadata中的ID/slot/BF16 weight和epoch，不重新生成路由，不注入新专家。

| slot | expert | owner |
|---:|---:|---:|
| 0 | 49 | 1 |
| 1 | 58 | 10 |
| 2 | 19 | 3 |
| 3 | 29 | 13 |
| 4 | 16 | 0 |
| 5 | 70 | 6 |
| 6 | 116 | 4 |
| 7 | 53 | 5 |

源代码按expert ID升序遍历并逐次index_add_，因此commit顺序固定16、19、29、49、53、58、70、116。每个专家结果先与对应BF16路由权重相乘并回BF16，再加到前一个BF16累加状态，并再次回BF16；没有以一次FP32总和代替逐次BF16累加。来源：[原模型实现](../mini_swe_operator_graph_v3_6_20261026_v1/source/modeling_qwen3_moe.py)、[原功能适配器](../swe_qwen3_bf16_functional_v1_20261026/bf16_adapter.py)。

[CPU预检](cpu_attempt1/RESULTS.json)对同token全部8个M1专家的gate/up/SiLU/product/down及源序前缀逐位检查通过。slot顺序负对照产生1157个不同的BF16元素，故不能按slot或返回到达顺序commit。该反例只属于此token，不作总体错误率。

## 新执行与前序复用

新建7个owner原生上下文（0、3、4、5、6、10、13），执行专家58、19、29、16、70、116、53的完整gate→up→SiLU→BF16乘积→down。每个专家原BF16权重由只读host后备offset绑定到实际HB；重算相关原分片和tensor SHA，明确BF16文件物理offset与临时FP32展开地址。host DMA、PCIe代理及HB commit后才发布驻留，原checkpoint不写入。

专家49复用[上一轮认证返回](../swe_qwen3_expert_tail_20261028_v1/REPORT.md)，在其认证完成边界后显式恢复源节点inbox，并对当前完整CPU专家参考重验返回body。不是重跑专家49，也不是宣称前后原生上下文连续存在。其他7个activation同样从上一dispatch认证的真实收件边界恢复。

本轮通用64lane归约树保留每lane的K步序与32/16/8/4/2/1树，独立lane乘法及加法批量表示为64×64点运算；每个元素仍显式FP32乘/加，非FMA或隐藏FP16矩阵运算。批量表示减少无关串行事件，不能将其与旧事件布局的代理周期差称为策略加速。gate/up K2048、down K768，BF16阶段边界保持原合同。

SiLU仍为host NumPy FP32表达式与原codec回BF16；不是目标NPU exp认证。所有codec和SiLU输入/输出经过显式HB/D2H/H2D服务，host计算与control成本仍null，不能当成完整时序已计入。

## 结果返回和commit门控

新增6条远端NoC消息，每条128 B头＋4096 B body=4224 B，共198个128 B包；专家16的owner即origin0，单列1次本地拷贝，不虚构NoC自发自收。专家49前序33包是复用证据，不重复计入本轮新流量。

新TX由真实HB BF16结果读取形成独立快照，显式SRAM drain后才允许发送。接收端先预留RX，本轮以目的节点可接收作为保守串行admission门控；不声称自然并发调度或拥塞收益。TX固定到全部尾包，RX固定到origin0 HB提交，接收读取验证原描述符、epoch、slot、weight、body SHA和参考字节。[返回账本](native_attempt1/RETURNS.json)。

source metadata的8条原描述符恢复到HB并读入SRAM，固定到全部8次commit。commit须满足metadata就绪、8份认证返回齐备、当前expert等于源顺序下一项、前一BF16前缀已HB提交、当前项未重复提交。缺一个返回、乱序、重复、前一项未完成均拒绝。

每次原生权重乘法后显式BF16编码并提交weighted缓冲，再读取上一BF16 accumulator与weighted值，原生FP32加法后再次编码、HB提交新前缀。新前缀完成才允许下一expert；旧accumulator、返回inbox、weighted暂存及metadata的该次reader保守保留到相应commit完成。最终前缀保留给downstream_residual，不提前退休。[commit账本](native_attempt1/COMMITS.json)、[last-reader](native_attempt1/LAST_READERS.json)。

## 验收证据

51项检查由7专家×5阶段（35项）、8个weighted结果和8个合并前缀组成，全部0差异。专家49返回单独复核，不虚计为本轮新专家执行。最终BF16输出：[final_token_BF16](native_attempt1/final_token_BF16.bin)。SHA256为cb74807888a5364973a4b10bc40137b20e9b45b1c3b26a32aa21189e8742a41f。

[远端独立审计](native_attempt1/INDEPENDENT_AUDIT.json)重读真实权重与完整CPU专家参考；另以独立NumPy64lane树核对7专家各投影的FP32驻留SHA，以整数BF16 RNE核对weighted和全部前缀，并核对原生库/NoC桥接SHA。依赖、DMA窗口、每个HB/SRAM读取者和释放、返回尾包和源序commit均重新检查。[本地因果审计](LOCAL_CAUSALITY_AUDIT_v2.json)核回收账本，不声称在Windows重读远端原权重。

原版audit_token.py逐descriptor扫描全部PCIe包，核查较慢；保留原版，audit_token_v2.py只将包按descriptor预分组，全部比较判据不变，已完成远端源审计与本地复核。初次102载荷封包早于最终审计回执，仅作原始交付；最终封包另纳入审计与本报告，成员数量以[DELIVERY](DELIVERY.json)和[本地完整性回执](LOCAL_DELIVERY_VERIFICATION.json)为准。

## 资源与范围

| 指标 | 本轮 |
|---|---:|
| 原生事件 | 84564 |
| FP32向量op | 69284608 |
| 32 B DRAM事务 | 12501896 |
| HB读 / 写 | 201037952 / 199022720 B |
| H2D / D2H | 198706176 / 66485120 B |
| 单节点SRAM峰值 | 3145728 B |
| 前序叠加新分配的保守HB量 | 231356096 B |
| 新NoC包 | 198 |
| 负对照 | 334项 |

单CH地址范围不超512 MiB，总HB不超8 GiB；host完整后备61064245248 B＋17 GiB运行/IO预留不超128 GiB。本轮保留已分配地址，不将干净权重退休资格称作已实现完整动态pager。

NoC输入峰值4 flit、输出1 flit、NI阻塞0，仅描述本次保守admission消息。NoC数值字节仍在原生尾包证书后复制，内部flit不是本负载BF16字节，不是逐flit数值验证。SRAM仍为聚合容量/服务，非逐Bank仲裁。

最终第8次commit的显式代理时刻98513699 ns；host SiLU/codec/control/gateway缺项使它不能作为完整系统时延。最终2048项对CPU源M1条件MoE组合逐位一致，不等于原GPU完整MoE结果或自主router逐位一致。M>1 batch归约21处/投影及softmax FP32差异继续保留。

本轮新增原生组合片段1，本线累计10；Sniper累计3，物理NPU0，无新GPU/agent/SWE/留出。步骤3整体仍PARTIAL，未认证完整层/模型、自然请求时序或HiBand/Sem-MoE收益。

下一步可接该token的MoE后残差及后续层依赖，再扩展独立decode样例。批量内核归约及host边界时序仍须各自验收，不由此次单token通过替代。

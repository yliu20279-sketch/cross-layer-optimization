# swe_qwen3：同token MoE后残差与下游交接

日期：2026-10-28。状态PASS_LIMITED_FIXED_TOKEN_POST_MOE_RESIDUAL；步骤3整体仍PARTIAL。

本轮完成同一R0002、prefill token0、第0层的MoE后BF16残差加法，绑定最终合并输出、残差输入及下游入口的真实HB驻留和last-reader。3个阶段各2048项对CPU源式及独立NumPy复算逐位一致；最终结果亦与已有GPU decoder输出的这个token逐位一致。没有新GPU调用，也不将单token一致推广到完整层或模型。

## 残差来源与BF16边界

原[DecoderLayer源码](../mini_swe_operator_graph_v3_6_20261026_v1/source/modeling_qwen3_moe.py)先执行decoder_input＋attention_output，再保留该值作为skip，随后post_attention_layernorm→MLP，最后skip＋MLP。故正确合同为：

residual_skip = BF16(decoder_input + attention_output)

layer_output = BF16(residual_skip + 已提交的BF16 MoE输出)

归一化后的moe_input不能用作skip。本例错误替换会产生2047个不同的BF16元素，见[输入预检](cpu_attempt1/RESULTS.json)。本轮未重跑attention或norm；两项前驱来自同一已保存fixture，先在本轮重建残差输入，再接上前序Top8组合。

fixture为原R0002的layer0_actual_fixtures.pt，SHA256 f78c166c14c6690f7482c7a26952adfefe265b5655aeed2b4b69d0049c6ac11f，经原MANIFEST核查。moe_input第0行与原dispatch body再次核对，避免把prefill/decode或不同token混接。前序[Top8结果](../swe_qwen3_token_commit_20261028_v1/REPORT.md)最终2048项BF16及第8次HB commit作为输入证书，不重新生成路由。

## 驻留与真实执行

原BF16、128 GiB host＋8 GiB HB研究overlay不变，原host8规范不改。

前序MoE合并BF16输出在源节点N0/CH0偏移235339776，原commit完成时刻98513699 ns。本轮在新原生上下文中，晚于该证书边界显式恢复同一地址及位型；恢复完成98514328 ns，有单独HB写服务。不是宣称上下文跨进程连续存在，也不把恢复成本算作前序算法收益。

decoder_input和attention_output的BF16位型经host DMA/PCIe/HB提交后，实际HB读回、D2H、原codec精确展开，再H2D至临时FP32区间。执行显式原生向量加法，FP32输出写HB、D2H、BF16编码、H2D，得到真正驻留的BF16 residual_skip。对skip和已提交MoE输出重复相同精度边界后执行第二次加法，得到BF16 layer_output。没有融合略过两次BF16舍入，也没有FP16/W4替换。

本轮2次2048元素原生FP32加法共4096向量op。post-add开始98544089 ns，原生加法完成98555080 ns，BF16结果HB提交98559114 ns。这些只是有缺项的显式代理时刻，host codec/control/gateway未完成目标时序认证，不能作为完整系统时延或加速比。

## last-reader与下游依赖

每个输入及工作区登记计划读取者。skip和MoE BF16原区间均保守保留到最终BF16结果commit后才允许退休；FP32输入保留到最后算术读取者，FP32输出保留到host编码/回写。记录的done_ns对跨host阶段为保守持有界，不声称最早可复用的精确CPU时间。[LAST_READERS](native_attempt1/LAST_READERS.json)。

生产者完成、输入驻留及request/phase/token/layer匹配全部满足后才允许加法。缺任一输入、错误epoch、提前退休/读取及SRAM早释放均拒绝。未改变其他token或原执行器。

最终BF16结果在N0偏移19922944，保留next_layer_ingress读取者。随后实际HB读入SRAM快照，再原生写入N0偏移20971520的layer1_ingress_BF16；入口HB提交98560410 ns后才发布layer1_input_norm_ready门控。原结果区间与快照保留到该交接提交才可释放。入口另有原生读回逐位检查，并继续保留layer1_input_norm读取者。

本轮没有执行layer1 RMSNorm算术，ready门控只是认证其输入可见；最终live入口未提前退休。不是跨NPU传输，也未运行新NoC。[依赖证书](native_attempt1/DEPENDENCIES.json)、[操作数门控](native_attempt1/OPERAND_GATES.json)。

## 数值、负对照与资源

| 阶段 | 元素数 | BF16不同数 |
|---|---:|---:|
| pre-MoE residual_skip重建 | 2048 | 0 |
| post-MoE residual加法 | 2048 | 0 |
| downstream ingress交接 | 2048 | 0 |
| 对已有GPU decoder_output同token诊断 | 2048 | 0 |

[状态](native_attempt1/STATUS.json)、[GPU诊断](native_attempt1/CAPTURED_GPU_DIAGNOSTIC.json)。GPU比较只使用既有采集，不是新增GPU测量；原prefill其他位置、batch归约及softmax FP32差异不改判。

27项负对照通过；573原生事件，4608个32 B DRAM事务，HB读/写各73728 B，SRAM峰值8192 B。新HB分配73728 B，叠加前序保守分配共231429824 B，单CH地址范围235343872 B，均未超CH512 MiB/总HB8 GiB。沿用完整host后备61064245248 B及17 GiB运行/IO预留，新增小型工作区不突破128 GiB。

[远端独立审计](native_attempt1/INDEPENDENT_AUDIT.json)重读原fixture、前序成员SHA、原生库及codec绑定；用原CPU BF16加法和独立NumPy FP32＋整数RNE复核，另核查所有原生依赖、host窗口、HB提交和释放顺序。[本地因果审计](LOCAL_CAUSALITY_AUDIT.json)只核回收账本，不声称在Windows重读远端fixture。完整性以[本地回执](LOCAL_DELIVERY_VERIFICATION.json)及[DELIVERY](DELIVERY.json)为准。

host codec/control时序仍null，SRAM仍为聚合服务，非逐Bank仲裁。当前是已记录dispatch/M1专家路径的条件单token收尾；没有自主router、全attention、完整层/模型、自然请求时序或HiBand/Sem-MoE收益认证。batch归约21处/投影和softmax FP32差异继续保留。

本轮新增原生片段1，本线累计11；Sniper累计3，物理NPU0，无新GPU/agent/SWE/留出/NoC。后续可单独验证layer1输入归一化或独立decode样例；既有差异不得由本次单token相等覆盖。

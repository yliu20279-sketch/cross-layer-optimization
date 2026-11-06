# swe_qwen3：专家49真实权重驻留与首个gate投影

日期：2026-10-28。总体状态：PARTIAL_NATIVE_GATE_SOURCE_NUMERIC_DIFFERENCE。

权重驻留、启动门控及缓冲生命周期有限核查通过；完整首个gate投影已运行，但回写BF16后与CPU原源码有1/768个输出不同，不能宣称源数值语义已通过。不是完整专家或MoE层PASS。

## 固定范围

沿用原模型BF16及128 GiB host＋8 GiB HB研究overlay，原规范host8不改。本轮只使用既有R0002第0层、row0/slot0的专家49（owner1）收件，完整gate投影1×2048→768。未启动GPU、agent、SWE、Sniper或读取新留出。softmax FP32七阶段差异继续FAILED_RETAINED（最大1.4901161193847656e-7）。

## 真实权重后备与HB绑定

从原safetensors index和16分片真实头部建立全模型不可变host地址映射。此为逻辑地址图，不能称为本轮已将61GB全部重新载入或逐分片重验。实际按key读取专家49的gate_proj/up_proj/down_proj原BF16权重，分别为[768,2048]、[768,2048]、[2048,768]，三者共9437184 B。重算相关完整分片SHA，对照原FIXTURE_WEIGHT_BINDINGS；同时核对tensor字节、文件物理offset、shape和BF16类型。[WEIGHT_BINDING](attempt1/WEIGHT_BINDING.json)记录来源与只读合同。代码没有原checkpoint写路径，未改变文件权限。

三组BF16权重经host DMA/PCIe代理后，在owner1真实原生HB写回调完成才发布驻留。host窗口固定到对应后备offset，提交之前禁止释放。gate权重随后从HB真实读取，经D2H返回host，用既有codec精确展开FP32，再显式H2D上传临时工作区。up/down原BF16权重保留驻留，但尚未展开或计算。

继承上一阶段已认证接收边界，将选定4224 B收件帧恢复到owner1同一本地地址；此次恢复有HB服务，但不是新NoC运行。恢复只覆盖本轮所需inbox，容量核算保守叠加父阶段所有822592 B分配，不表示原生上下文跨进程持续运行。后续读取绑定原帧body SHA、expert/slot/owner。

## 计算与last-reader依赖

计算启动要求metadata、inbox、BF16权重和展开工作区全部就绪；逐项缺失均拒绝。执行顺序中的原生事件依赖绑定上传commit与后续HB读，不以“已创建张量”替代权重到达。

使用64输出×64 K分块，完整遍历2048个K及768个输出，显式FP32乘法、K顺序加法，最终BF16舍入；没有FP16矩阵运算或W4替换。每个SRAM输入块/权重块有64次算术读取者，最后一次乘法完成前禁止释放；12个输出tile全部完成才允许展开HB工作区退休。原inbox仍有up_proj待消费，因此提前释放被拒绝，up/down权重继续保留。gate输出写入HB后尚未接入SiLU或后续消费者。

来源：[RESIDENCY](attempt1/RESIDENCY.json)、[HB_LAST_READERS](attempt1/HB_LAST_READERS.json)、[ARITHMETIC_LAST_READERS](attempt1/ARITHMETIC_LAST_READERS.json)、[TRANSFERS](attempt1/TRANSFERS.json)、N01原生事件/SRAM日志。启动/提前复用等9项负对照通过。旧parent input_ref仍是描述符逻辑引用，本轮通过单独物理地址绑定兑现选定收件，不修改父协议。

## 数值结果与未通过原因

原生回调数值与独立NumPy逐K FP32乘加复算逐位一致，768项全部检查。BF16舍入也由独立整数RNE复算一致。但与CPU原源码torch.nn.functional.linear比较，第50号输出不同：

| 对照 | 值或BF16 bits |
|---|---:|
| 顺序FP32累加 | 0.000283275730907917 |
| CPU FP32 linear | 0.00028322916477918625 |
| FP64诊断 | 0.00028323161677690223 |
| 目标顺序路径BF16 bits | 14741 |
| CPU原BF16 linear bits | 14740 |
| FP32 linear / FP64诊断舍入BF16 bits | 均14740 |

差异1/768，最大BF16绝对差1.9073486328125e-6。[NUMERIC_DIAGNOSIS](attempt1/NUMERIC_DIAGNOSIS.json)支持“顺序FP32归约误差跨过BF16舍入边界”的解释；尚未证明原CPU内核的确切归约树，更不能据此推断原GPU专家中间值。FP64仅诊断，未改变模型或实际路径，不事后放宽容差。

因此本轮完成了首个完整专家算子的执行与验证，但数值准入未通过。原router的短样例乘加通过不能直接外推专家投影。

## 资源与证据

原生100478事件、790120个32 B DRAM事务，HB写15744128 B、读9539712 B；H2D15736832 B、D2H3149952 B。单节点SRAM峰值3145728 B；父阶段叠加本轮新分配的保守HB量16566720 B，未超8 GiB，单CH地址范围亦未超512 MiB。host完整后备映射加17 GiB运行/IO预留不超128 GiB。

代理compute_start=8345187 ns、compute_done=9847994 ns，仅记录显式服务及原生片段；不作为完整BF16性能指标。host codec、header/control、缓存维护及gateway成本仍null；未新采Sniper ROI。BF16输出是从模拟HB数值影子导出的离线codec检查，没有输出D2H/encode时序认证。SRAM只有聚合容量/服务模型，未认证逐Bank仲裁。此次无需新NoC，不能称为专家算子与上一NoC在同一持续执行器内端到端运行。

[远端独立审计](attempt1/INDEPENDENT_AUDIT.json)验证真实权重SHA、独立NumPy算术与原执行库身份；[本地因果审计](LOCAL_CAUSALITY_AUDIT.json)核对事件、依赖、DMA窗口和缓冲释放，不声称本机重读原权重。证据全部成员SHA见[本地回执](LOCAL_DELIVERY_VERIFICATION.json)，数量以[DELIVERY](DELIVERY.json)为准。

本轮新增原生模拟片段1，本线累计7；Sniper累计3、物理NPU0、新GPU/agent0。独立因果审计PASS只针对上述门控与实现复算，不覆盖失败的源BF16数值比较。

## 下一步

保持当前失败证据和协议，先在独立CPU候选目录研究源BF16 linear归约边界：检查可实现的分块/归约方法，使用开发fixture验证后再冻结目标候选。禁止针对第50号输出打补丁，或因一个样例一致便声称通用BF16 GEMM支持。数值候选通过后再接up_proj、SiLU乘法和down_proj，并补gate输出下游last-reader及结果返回/源序合并。SWE修复仍独立。

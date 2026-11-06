# 真实输入功能推进后的目标映射约束

此为候选软件/映射合同，不是当前目标硬件执行证书。原BF16、host128 GiB/HB8 GiB overlay固定，目标V3.6原FP16阵列规格不改。NPU运行0，cycles保持null。

## BF16矩阵软件候选

bf16_vector_bridge.cpp复用原NPUSim BF16 codec，逐BF16值扩展为FP32，执行分开的FP32乘法与加法，按K升序持续累加，结束回写BF16。编译禁fast-math和FMA收缩。不走FP16阵列。短请求router的prefill19与decode1均对捕获GPU logits逐位一致，仅支持这一实际样例范围。

mapping_attempt1/RESULTS.json记录真实标量工作量：prefill分别4980736次FP32乘/加，decode分别262144次。decode/encode次数是当前host函数调用计数公式，不是已发行的目标ISA指令；BF16转换的目标软件指令及费用仍未落地，不能直接按16ops/cycle除出总周期。64宽K分块为逻辑循环，单tile8576 B只是候选BF16操作数＋FP32累加载荷公式，不是函数实际SRAM分配观测或整层峰值，完整生命周期/双缓冲/Bank仲裁另验。

## EP16 dispatch/return数值顺序

owner=e mod16；origin=t mod16，单forward重置，此为此前候选。每个assignment保留request/forward/layer/token/slot/expert/owner/origin标签。

拆分到不同origin后，专家输入须重建原torch.where的slot/token顺序。为本轮功能检查保持原专家batch形状；以后目标tile切分的矩阵归约与数值影响必须另验，不能借本检查默认通过。

专家可按设备合法调度顺序完成，返回值在origin按源专家升序commit到BF16累加输出；不能按rank或到达顺序直接index_add。源顺序和反例见mapping_attempt1/RESULTS.json：preserved-order两阶段逐位一致，naive-rank两阶段均不同。当前host模拟仅重排已计算的贡献，没有运行NoC或故障/乱序消息系统。

origin的完成记录和缓冲必须纳入容量及依赖：一个token最坏8份2048维BF16贡献为32768 B，尚不含metadata、residual、其他工作区。可用逐token/逐tile门控限制驻留，不能假设这些缓冲免费；没有足够容量就等待/反压，不能提前释放下一消费者。

## 其他算子与门槛

- RMSNorm/softmax/RoPE/SiLU/TopK：保持原混合精度边界，FP32 vector/reduce只是映射候选。特殊函数实现、归约树及成本尚未认证。
- TopK：固定route回放可读已释放实际ID；自主router不能注入记录。非平局身份必须一致；边界平局保留SOURCE_BACKEND_TIE_UNRESOLVED，不能用连续误差容差掩盖专家集合变化。
- Attention：已在真实输入下验证适配器对同CPU原函数，但没有认证目标TP16拆分归约、KV四份复制、SRAM attention tile或跨backend逐位一致。
- 权重/缓存/通信：完整host只读后备→HB共享cache→SRAM，所有分页与collective完成后才能消费；本轮尚未接通这些设备事件。

下一项应当先实现上述软件候选的目标原语/codec成本及有界单op完成门控，再扩展层内事件；两层需要另登记原权重与输入参考。不得把本轮CPU完整层对照或旧SWE评分当目标单层执行PASS。

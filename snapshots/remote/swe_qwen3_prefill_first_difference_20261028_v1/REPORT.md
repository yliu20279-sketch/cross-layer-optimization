# swe_qwen3 prefill 最早差异定位（2026-10-28）

状态：PASS_LIMITED_FIRST_DIFFERENCE_DIAGNOSIS；步骤3整体仍PARTIAL。定位完成，未修复或放宽任何差异，未改原适配器。原BF16、128 GiB host＋8 GiB HB不变。

## 结论

需要区分内部FP32首次差异和首次传至下游的BF16差异。

1. 最早内部差异在输入RMSNorm的 `FP32 mean(square)`：同一输入及逐元素square完全一致，但19行方差有9行不同，最大2.9103830456733704e-11。相同输入的独立mean探针复现9行差异；相同epsilon输入的rsqrt探针也有差异。因此不是仅靠修复后续GEMM即可宣称所有FP32内部量一致。
2. 本例输入RMSNorm回BF16后全部逐位一致，包括scale输出。这批内部差异在该边界被舍入消除，不能将4249个最终输出差异归因于这些方差差异。
3. 最早持续到下游的BF16差异位于Q/K/V投影GEMM：Q有74、K有5、V有3个元素不同，最大分别0.00048828125、0.0001220703125、1.1920928955078125e-7。CPU/GPU使用完全相同的BF16输入和原BF16权重，独立等输入探针再次复现相同数量。因此已排除输入RMSNorm输出不一致作为这三组差异的原因；更细的GEMM累加/内核规则仍未定位或修复。

## 差异传播与路由

自由运行下：Q head norm输出120处、K head norm输出5处；masked scores28处，attention FP32 softmax2696处、BF16概率24处；PV287处、attention输出1312处；残差650处；post-attention norm输出568处；router logits13处；最终Top8 slot10处不同。各阶段不同数不代表独立错误，也不能相加。

新GPU诊断的attention输出、MoE输入、router logits、Top8全部与原R0002 GPU采集逐位一致。CPU的9个前半层/路由阶段二进制与之前连续两层运行的CPU参考逐字节一致。因此定位与原4249输出/10路由差异属于同一输入/同一路径；本轮没有重新计算完整专家尾链，4249仍引用此前完整层检查，不冒称本次重新验证完整层输出。

10个slot差异分布在token1/12/14/15，分别2/5/1/2处。token1、12、15的专家集合相同，slot变化涉及内部平局；token14更换一个专家且第8/9名存在边界平局。token12还伴随上游logit变化。不能把10处全部归因于QKV投影，也不能把它们全部视作不同专家集合；原CPU通用TopK不稳定排序语义仍是独立因素。此前CUDA tie规则host候选与此自由运行CPU通用TopK路径应分别记账。

FP32 softmax差异完整保留，本轮没有调整或消除它们；本例attention softmax同时承受上游scores变化，不等于之前同logit路由softmax差异计数。

## 证据、范围与后续

诊断只加载9个前半层/router参数张量，使用H100 GPU0作外部参考，峰值GPU allocated73374720 B；目标GPU仍0。固定torch2.6.0+cu124、单线程CPU、TF32关闭、BF16 reduced-precision reduction关闭，保持原采集设置。1次有界GPU参考诊断，无完整模型、SWE/agent、新留出、目标原生或物理NPU运行；累计原生14/Sniper3不变。

来源：attempt1/CHECKS.json（50自由阶段及等输入探针）；attempt1/FILES.json（100个阶段二进制及SHA）；attempt1/PROVENANCE.json（fixture、源码、checkpoint完整分片SHA）；LOCAL_AUDIT.json（本地NumPy独立复核）；../swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1/CHECKS.json（原4249输出差异）。diagnose.py执行前FREEZE.json固定代码，失败的只读fixture枚举命令未运行模型，不计诊断运行。

下一处研究入口是同输入Q/K/V BF16 GEMM的源GPU归约/舍入规则；随后分别核对Q/K head norm与attention矩阵。仅识别最早算子不能证明后续仅有一个根因，不应直接替换全层归约策略或按输出修补。

用户本轮明确批准上传旧报告；旧报告已成功上传113，远端与本地SHA均为 a2baed270e05ad0b80449178f4b3c4bedd0476ffa093b5b51e1158baa042c128。旧自动审批拒绝保留为历史，不再阻断该已批准操作。

# 步骤3新增执行：BF16残差与RoPE向量原语（2026-10-29）

本轮实际新增1次NPUSim/Ramulator原生事件运行，非旧证据复核。状态PASS_LIMITED_NATIVE_BF16_VECTOR_FRAGMENT，步骤3仍PARTIAL。

独立vector.cpp以原BF16输入解码为FP32，显式乘/加，再通用RNE编码BF16；不调用PyTorch算术求输出、不用FP16或输出补丁。run.py将实际字节载入SRAM，计算回调调用C原语，HB写提交依赖计算完成。RoPE遵守两次BF16乘积各自舍入、再BF16加法的源边界，不融合FMA。

R0002两层prefill19/decode1共四组：每组attention后残差及Q/K的cos乘、sin乘、合并，共28项严格比较逐位一致；56项SRAM提前free/HB提前退役均被拒绝。RoPE两项乘积到最终加法使用本进程实际HB结果，未恢复其参考中间值。

原生344事件、175360个32 B事务、634880逻辑向量ops；SRAM峰值466944 B、HB3072000 B。事件、依赖、操作数量与区间last-reader独立复核见INDEPENDENT_AUDIT.json；所有原始事件在attempt1/N00。乘加宏含独立C的BF16编解码数值，但其整数指令与控制成本未计费，不能把代理时间视为完整BF16时序。

边界：Q/K输入仍以CPU原GEMM/head norm重建，cos/sin来自既有fixture，起始残差输入来自已认证CPU阶段。没有将新原语接回完整层/两层连续运行，也未修复QKV GPU归约、RMSNorm或softmax；本轮不声称四项全部完成。既有GPU softmax FP32与完整层差异均保留。当前是N0原生存储/计算完成门控的软件原语片段，非物理NPU、TP/EP或完整系统时序。

原BF16、host128 GiB/HB8 GiB不变。无新GPU、SWE/agent/留出/NoC运行；本轮新增原生1，按前次累计14更新为15，Sniper3、物理0。

来源：FREEZE.json、vector.cpp、run.py、attempt1/RESULTS.json、LAST_READERS.json、RESIDENCY.json及原生事件；输入参考来自../swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1/FILES.json。下一步将这套向量原语接回连续adapter，随后处理norm归约，不能仅重命名host回退。

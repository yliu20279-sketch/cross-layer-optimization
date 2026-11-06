步骤4最终有限范围交付（2026-10-31）

原步骤4的DiT layer0 CPU功能适配范围已通过；本次同时修复旧原生router片段数值差异。不能将此结果写成完整层目标原生或TI2V端到端通过。

完整单层：同一已见example_4、step0/layer0双CFG，98869行、全真实K/V，attention输出/FFN输入/FFN输出/postnorm/层输出5类逐位一致；30944项独立审计通过。原始证据见../lingbot_step4_stagewise_20261030_v5/completion_receipts/。完整层依然是CPU软件适配，并非纯NPU。

本次原生片段：原cond row0，5路交错K8 split-K、软件fmaf及顺序FP32归约；128个FP32 logits对原GPU及本地独立Windows CRT标量复算逐位一致，旧121/128差异修复。CPU数值在NPUSim/Ramulator事件完成后暴露给消费者。独立审计75445项通过，10283事件、33312个32B事务、525440个向量操作记账，SRAM峰值3616B；4项原生guard及3项独立负对照通过。8份小片段载荷全量取回，逐文件SHA与113一致。POSIX其他用户可读/目录可遍历通过，未做跨账号登录。

首次缺onnx导入失败和第二次FMA事件计数漏改失败均保留。修订仅将FMA登记64改128；没有改变数值算法或放宽门槛。既有四负载虚拟环境Torch2.6.0+cu124/onnx/safetensors被只读复用，无共享安装更改。用户已批准本对话所有包上传，先前具体包上传拒绝是历史。

保持原混合BF16/FP32、host128/HB8、目标GPU0；本轮外部GPU0、完整模型0。新原生尝试2（1计数失败、1成功），LingBot累计3（含旧片段1），另1次导入失败未进入原生。物理NPU0。

未认证：完整层所有算子的目标原生lowering、CPU codec/PCIe/gateway/NoC/SRAM Bank完整时序、48层40步目标闭环、VLM/VAE和完整TI2V。FMA按2向量操作仅代理记账，实际目标FMA成本未校准；不报告HiBand/Sem-MoE/Bank策略收益。数学域表host访问成本仍须计费。

源与结果：corrected_source/、countfix_evidence/、audit_countfix_local.py、INDEPENDENT_AUDIT.json、LOCAL_VERIFICATION.json。旧失败见attempt2_evidence/及113原目录；远端成功目录/mnt/sda1/h3240101068/lingbot_step4_native_repair_countfix_20261031_v6。

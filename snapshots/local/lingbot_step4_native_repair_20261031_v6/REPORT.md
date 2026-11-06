步骤4剩余工作与隔离原生router修复准备

已确认：双CFG layer0/step0完整98869行单层CPU功能及30944项独立审计通过，详见../lingbot_step4_stagewise_20261030_v5/COMPLETION_CHECK.md。原协议PROTOCOL.json限定DiT layer0功能host fallback，不要求48层40步/VLM/VAE目标全链；不能把该有限范围扩写为TI2V。

遗留原生片段：旧顺序FP32乘加的128 logits有121项与GPU不同，旧结果不撤销。新源码复用既有NPUSim/Ramulator完成门控，在CPU执行5路交错K8 FMA和FP32顺序分区归约，严格核对GPU及独立标量参考。FMA事件按2向量操作作代理记账，实际目标FMA成本未校准，不作时序结论。单线程300秒上限、目标GPU0、host128/HB8、旧目录不覆盖。

本地源码语法解析通过；数值及事件运行未执行，不能认定修复成功。4346B源码包上传被自动审批拒绝，理由为缺少对此新payload的明确外传授权。包SHA256：30ee7cb6a5f5dba14b2b2ef7d18c00982fbf288c257c54fbfdb07e2961d4d242。无绕过或间接上传。

下一门：明确批准该包后隔离上传、核SHA、有界运行；独立审计128个FP32位值、事件依赖和32B事务守恒、HB512MiB/4MiB SRAM生命周期；失败立即保留。不放宽门槛。完整层目标lowering、CPUcodec/PCIe/NoC/Bank时序仍不是本CPU功能PASS所覆盖的内容。


授权后实际执行：原4346B包上传SHA一致。首次在LingBot环境导入onnx失败，保留日志；已有四负载环境Torch2.6.0+cu124/onnx/safetensors兼容，改用该环境后实际执行1次原生片段。数值断言通过后，事件计数断言停止，未保存最终数值载荷，不认定通过。原因：生成源码时FMA登记仍为64，断言要求128。独立本地复核10283事件、33312个32B事务、依赖及SRAM生命周期通过，峰值3616B；实际vector_ops263296与预期525440相差262144，恰为FMA第二个操作数。失败现场留113及attempt2_evidence。

计数修订包4357B，SHA ecb7bc929d177c0451201ba8d37eaf37efea53d55cd47c42ac8e499a0d255d0f，仅将该事件登记改128，数值算法未改。新payload上传被自动审核拒绝，要求明确授权；未执行上传、未绕过。原完整单层CPU PASS不受影响，原生修复仍未验收。

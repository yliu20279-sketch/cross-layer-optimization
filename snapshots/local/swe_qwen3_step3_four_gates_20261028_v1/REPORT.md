# swe_qwen3 步骤3：四项功能门槛收尾（2026-10-28）

结论：四项有界功能/因果检查已完成，状态 PASS_LIMITED；步骤3整体仍 PARTIAL。原BF16、128 GiB host＋8 GiB HB保持不变。此次不是纯NPU完整层、TP16/EP16或完整系统时序认证。

## 四项结果

1. 前半层：输入RMSNorm、Q/K/V、head norm、RoPE、KV、masked attention、FP32 softmax、O投影、残差、post-attention norm及router，四个phase/layer组合共68项逐阶段检查逐位一致。见 coupled_attempt3/FRONT_STAGE_AUDIT.json。
2. 数值缺口：依据oneDNN v3.5.3源码重建BF16 GEMM的K分块与奇偶累加顺序，258组gate/up/down、645120元素对本CPU源实现零差异。M1保留64lane规则，K19等尾部通用处理。旧失败和旧batch差异保留；不证明任意形状或GPU一致。见 batch_attempt2/RESULTS.json、source_gemm_v2.cpp、onednn_source_v2/MANIFEST.json。
3. 真实prefill/cached decode：既有R0002的19-token prefill及1-token decode，原权重连续执行层0和层1；4个层输出与8个KV检查全部逐位一致，56个阶段文件与独立CPU参考一致。层1参考为本次CPU重建，非原GPU采集。见 reference_attempt1、generated_attempt2、coupled_attempt3 的 CHECKS/FILES/PROVENANCE。
4. 连续依赖：同一进程2次层间HB交接，无恢复中间Golden；decode读取本次prefill生成的KV并追加19→20。权重只读host后备、32 MiB共享HB槽、759个权重版本及矩阵宏、2327个tensor节点与last-reader已审计。末层输出留给layer2，KV留给后续decode。见 LAYER_HANDOFFS、KV_EVENTS、WEIGHT_SLOT_VERSIONS、NODES、LAST_READERS。

## 执行与边界

选用 coupled_attempt3：139420事件、107915094个32 B原生RAM事务；SRAM峰值703744 B，HB地址范围102833632 B。759个独立C FP32矩阵软件宏与原生NPUSim/Ramulator存储回调耦合；norm、softmax、SiLU、布局及部分向量运算共772次显式host回退。CPU/codec/control成本为null，代理结束时间不准入完整时序或收益结论。PCIe使用解析packet-run账本 LINK_DESCRIPTOR_RUNS.json；空的兼容packet文件不作证据。无新增NoC。

这是16 NPU架构内的N0串行诊断，不替代最终TP/EP映射。独立审计核对实际事务、容量、依赖、版本重用、KV与连续交接；核对checkpoint分片SHA并用NumPy挑战独立C内核。见 coupled_attempt3/INDEPENDENT_AUDIT.json、BUILD_BINDING.json、ADAPTATION_CHECKS.json。

原GPU层0prefill仍有4249个输出元素、10个路由位置差异；既有softmax FP32差异继续保留。不能以CPU逐位一致替代原GPU全语义一致。未证明完整模型、物理BF16、完整host服务时序或HiBand/Sem-MoE策略收益。

失败保留：attempt1布局视图错误；attempt2历史模块导入将线程数1改为4；attempt3恢复冻结的单线程合同，无放宽容差或单输出补丁。审计v1误指失败目录，v2仅修正路径。CPU启动环境、K19尾部和源码下载失败均保留。

本轮原生运行3次（2失败、1通过）；累计原生14、Sniper3、物理NPU0。无新GPU、agent、SWE任务或留出正文访问。

来源：本目录冻结协议与上述机器回执；oneDNN固定版本源码 https://github.com/oneapi-src/oneDNN/tree/v3.5.3/src/cpu/x64/gemm 。源文件字节SHA与API来源见 onednn_source_v2/MANIFEST.json。

# swe_qwen3 新BF16向量原语接回连续两层（2026-10-29）

状态：PASS_LIMITED_CONTINUOUS_VECTOR；步骤3整体仍PARTIAL。本轮实际新增1次连续原生模拟事件运行，并非重验旧输出。原BF16、128 GiB host＋8 GiB HB保持不变。

## 新增实现与验证

continuous_adapter.py继承此前连续adapter，将BF16 add/multiply入口替换为vector.cpp独立C原语：BF16解码、显式FP32乘/加、通用RNE回BF16。实际输入字节从HB加载SRAM；C回调受native compute事件门控，HB输出提交依赖compute完成。对广播/非连续视图显式物化布局并保留父节点。没有按单个输出修补，没有调整容差。

因此RoPE两次BF16乘后再BF16加、attention与MoE后残差、norm缩放及其他经过这些入口的乘法，均在同一进程中使用新路径；不是只在独立fragment求值。其余norm归约/rsqrt、softmax、SiLU、layout等仍有host语义回退。

R0002真实19-token prefill→1-token cached decode，原权重层0→层1：4层输出及8 KV共12项严格比较全部逐位一致；保存56阶段全部与此前CPU参考逐字节一致。374个新向量节点按执行顺序逐项核对旧路径对应add/mul哈希，全部一致。独立NumPy对C原语新增131072元素有限域挑战通过。见attempt1/CHECKS.json、FILES.json、NATIVE_VECTOR_NODES.json及INDEPENDENT_AUDIT.json。

## 因果、驻留与容量

同进程2次层间HB交接均restored=false；decode读取本次prefill生成的KV，两层分别19→20追加，共4次KV事件。新增输出在compute完成后HB commit，下游读取受对应producer门控；每个向量节点有SRAM提前free负对照。输入读取者、节点readers、退休/保留状态、HB区间及所有显式事件依赖经独立审计。末层输出和KV保留给下游/未来decode，不提前退休。见LAYER_HANDOFFS、KV_EVENTS、LAST_READERS、NODES。

本轮139081事件、108211456个32 B原生RAM事务；SRAM峰值703744 B，HB地址范围105929216 B。759个矩阵宏/权重版本；374个新向量宏；host回退调用772→398（相同输入/两层范围）。该计数下降不是时间或收益测量。

## 保留边界

对原GPU的层0prefill仍保留4249个输出元素及10个路由slot差异；softmax FP32差异未更改，不以CPU一致替代GPU一致。GPU GEMM规则未修复，旧192分段候选未接入。

实际数值回调在服务器CPU执行，native指模拟器SRAM/HB/compute事件；C编解码/整数/控制成本尚未全部计费，CPU回退成本null。仍是N0串行混合路径，非纯NPU、TP16/EP16、完整系统时序、物理性能或HiBand/Sem-MoE净收益认证。PROTOCOL.json为运行中补充的范围说明；FREEZE.json才是实际运行前代码冻结，不冒称说明文件预登记。

累计原生由15更新为16，Sniper3、物理NPU0。本轮GPU/agent/SWE/新留出/NoC运行均0。已获批准的上一轮审计、状态和报告补充文件已上传113；旧拒绝仅为历史。

来源：本目录FREEZE.json、run.py、continuous_adapter.py、vector.cpp；attempt1/COUPLED_STATUS.json、RESULTS.json、事件与上述账本；INDEPENDENT_AUDIT.json。下一步应继续将norm归约/特殊函数明确lowering，并分别处理GPU矩阵归约，不把本次有限通过升级为步骤3全通过。

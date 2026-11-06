# 步骤3：FP32 softmax软件原语接回连续两层

状态PASS_LIMITED_CONTINUOUS_SOFTMAX，步骤3仍PARTIAL。实际新增两次原生模拟片段运行：continuous_attempt1失败保留，continuous_attempt2通过。原BF16、128 GiB host＋8 GiB HB保持不变，无本轮GPU、SWE/agent、新留出或NoC运行。

## 新增实现与依赖

softmax_kernel.cpp以独立C控制流程实现最后一维FP32 max、减max、向量exp、16路累加和横向归约、倒数、乘法归一化；BF16输入在C内解码，输出保持FP32。softmax_adapter_v2.py替换原host softmax求值入口，实际字节从HB读入SRAM，计算完成后才提交HB并暴露下游；提前free输入负对照拒绝。

exp明确依赖已安装libtorch_cpu.so导出的SLEEF `Sleef_expf16_u10avx512f`，库SHA记录在MATH_DEPENDENCY.json；没有调用torch张量softmax内核求候选结果，但不是独立重写exp数学算法，也不是可直接部署的目标NPU exp指令。stage_reference.cpp单独重建源softmax的16路exp映射，与候选共享SLEEF。因此exp中间阶段是映射一致性检查，非独立数学库认证；最终FP32概率严格对照未修改torch.softmax。

限定最后一维19/20/128、有限输入；其他几何/非有限输入明确拒绝。支持当前有限值causal mask，未认证任意上下文长度、负无穷mask或特殊值语义。

## 验证与因果

- 72组独立输入、712088元素最终FP32概率逐位通过，覆盖19/20/128维、1/19/513行、BF16/FP32、随机/均匀/大动态范围/有限值mask。
- 原R0002的19-token prefill→1-token cached decode，连续原权重层0→1：8次softmax的max/exp/sum/inverse/probabilities共40项逐位通过，且8个FP32概率哈希与此前CPU路径一致。
- 保留此前16次norm/64阶段与374个向量节点检查；56个保存阶段与旧CPU参考逐字节一致，4层输出和8 KV共12项严格检查通过。
- 2次真实HB层间交接无Golden恢复；4次KV追加，decode读取本进程prefill生成的KV并19→20追加。输入readers、计算→提交→下游依赖、退休/保留区间、SRAM/HB容量经独立审计。

来源：continuous_attempt2/SOFTMAX_NODES.json、SOFTMAX_CHECKS.json、NORM_CHECKS.json、CHECKS.json、FILES.json、LAYER_HANDOFFS.json、KV_EVENTS.json、LAST_READERS.json与INDEPENDENT_AUDIT.json。中间阶段保存比较记录，非全量exp/sum数组原始采集，不冒称可以在本地逐字节重验未交付的中间数组。

## 失败保留与范围

probe1的8路实现对attention/router分别119/1116个FP32差异，未采用。probe2的16路候选全部匹配。continuous_attempt1将单独torch.exp误作softmax内部exp oracle，首阶段558项不同而停止；修改仅是以源码内部16路映射重建阶段参考，候选数值代码未变，最终概率仍严格对未修改torch.softmax。原失败和运行前冻结保留，不通过放宽容差。

CONTROL_FREEZE.json有一次writer将driver哈希误标为kernel文件，原记录保留，正确清单CONTROL_FREEZE_V2.json与FREEZE_CORRECTION.json独立说明；集成实际代码以运行前CONTINUOUS_V2_FREEZE.json为准。源码依据及本机头文件绑定见source_headers/MANIFEST.json：
https://github.com/pytorch/pytorch/blob/v2.6.0/aten/src/ATen/native/cpu/SoftMaxKernel.cpp

选用运行138163事件、107954664个32 B事务，SRAM峰值703744 B、HB地址范围101820544 B。759矩阵宏、374向量宏、16 norm宏、8 softmax宏；host回退350→342只是调用数，不代表耗时/策略收益。

原GPU层0prefill仍4249输出元素、10路由slot差异；GPU GEMM及softmax FP32差异保留。仍是N0串行服务器软件数值回调＋模拟器门控，非物理NPU、TP16/EP16、独立exp算法或完整时序；SLEEF、整数codec、控制及临时分配没有完整目标成本。继承的COUPLED_STATUS scope仍含旧norm/softmax host文字，以新节点和本报告为准，原回执不改。

累计原生19（此前17＋本轮失败1/成功1）、Sniper3、物理NPU0。其余host特殊函数/布局、GPU矩阵归约与完整时序尚未完成。

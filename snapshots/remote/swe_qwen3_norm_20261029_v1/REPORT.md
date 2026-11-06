# 步骤3：FP32归约/rsqrt软件原语接入连续两层（2026-10-29）

状态PASS_LIMITED_CONTINUOUS_NORM，步骤3仍PARTIAL。实际新增1次连续原生模拟事件运行，原BF16、128 GiB host＋8 GiB HB不变；无新增GPU、SWE/agent、留出或NoC运行。

## 新增实现

norm_kernel.cpp显式BF16解码→FP32 square→cascade8分层归约/mean→FP32 epsilon→sqrtf后FP32倒数→FP32逐元素归一化→RNE回BF16；最后调用此前原生BF16乘法缩放。norm_adapter.py替换rmsnorm入口，不调用PyTorch求结果；PyTorch仅在计算后用作严格阶段oracle，不注入输出。当前固定K128/2048、epsilon=1e-6，其他几何显式拒绝；数值覆盖限已验有限输入，非特殊值或任意维度认证。

原语C回调由native compute门控，实际BF16输入从HB读到SRAM，FP32 scratch显式分配与服务，BF16输出提交HB后才暴露给后续缩放/读取者。提前释放norm输入的负对照被拒绝；last-reader、所有显式事件依赖及retirement/保留状态经审计。

归约依据固定PyTorch v2.6.0 SumKernel.cpp的分层cascade结构，当前CPU有效宽度8；不是假定GPU采用该规则。顺序/简单树及宽度16失败保留在probe1/probe2，不采用按输出修补。参考来源：https://github.com/pytorch/pytorch/blob/v2.6.0/aten/src/ATen/native/cpu/SumKernel.cpp 。rsqrt为C sqrtf后取倒数的软件组合，不宣称目标具有硬件rsqrt或GPU近似语义。

## 实际验收

R0002真实19-token prefill→1-token cached decode，原权重层0→1，同进程连续执行：

- 16次norm调用，每次variance、epsilon、rsqrt、normalized BF16共64项逐位一致。缩放结果同时受374个向量节点对旧CPU路径的哈希检查覆盖。
- 56个保存阶段与原CPU参考逐字节一致；4层输出与8 KV共12严格项通过。
- 2次真实HB层间交接，4次KV追加，decode使用本次prefill生成的KV，19→20；无中间Golden恢复。
- 128/2048维、1/19/513行随机/零/常数输入控制：72项、3489018元素逐位通过；另继承131072元素C BF16乘加独立挑战。

见continuous_attempt1/NORM_NODES.json、NORM_CHECKS.json、CHECKS.json、FILES.json、KV_EVENTS.json、LAYER_HANDOFFS.json、LAST_READERS.json及INDEPENDENT_AUDIT.json。norm中间阶段保留比较计数而非完整FP32数组，不宣称本地可逐字节重放这些数组；oracle仅CPU源码，不是原GPU norm内部采集。

## 事件、容量与限制

138171事件、107954664个32 B原生RAM事务；SRAM峰值703744 B，HB地址范围101820544 B。759个矩阵宏、374个向量宏、16个norm宏。host回退398→350，是调用数而非耗时/收益；已移除host rmsnorm入口，softmax/SiLU/layout等仍有回退。

原GPU层0prefill仍保留4249输出元素、10路由slot差异；GPU GEMM归约候选未接入，softmax FP32差异未改。整体仍N0串行软件数值回调＋模拟器事件，不是物理NPU或TP16/EP16。FP32 scratch流量与逻辑运算是宏级代理，C整数codec、sqrtf实现、临时分配/控制与oracle开销非完整目标时序；不得据代理结束时间宣称性能。

COUPLED_STATUS.json继承的scope字符串仍列RMSNorm host回退，属于未同步的旧说明，以NORM_NODES、HOST_FALLBACK_OPS及本报告覆盖范围为准；原回执不改。CONTINUOUS_FREEZE.json为实际运行前集成代码冻结；初期候选探针与失败按原目录保留。

累计原生17、Sniper3、物理NPU0。下一缺口仍是GPU GEMM规则和其余host特殊函数/布局服务及完整时序，不能把本次CPU数值闭链升为整个步骤3完成。

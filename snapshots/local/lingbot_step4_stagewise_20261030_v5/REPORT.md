# LingBot步骤4续作：稀疏专家split-K修复与两阶段全层验收

当前仍为PARTIAL。旧全查询验收已因真实数值差异停止；本轮修复了该失败分块，并恢复新的两阶段CPU验收，尚无完整单层通过结论。保持目标GPU0、原混合BF16/FP32、host128GiB/HB8GiB，不放宽逐位门槛；refiner仍排除。

## 已确认的失败与修复

旧任务在条件分支前11776行通过后，于[11776,11840)分块的FFN输出发现4个BF16差异，最大绝对差0.015625；位于块内token58、列91/388/1475/1602。attention输出与FFN输入已经通过，任务按合同停止，旧全量审计未运行。这不是下载或进程中断。

CPU复现确认共享专家输出、Top8槽位和权重均一致。外部原始dispatch批量诊断定位首差在专家28的up GEMM一个BF16元素，后续专家输出77个元素不同，经加权归约后表现为4个FFN差异。SiLU枚举全部65536种BF16位模式，对全部65280个有限输入与CPU实现逐位一致，故未采用额外SiLU查表补丁。

实际矩阵批量M=148时，源GPU gate/up使用6路并行split-K、FP32工作区。K=2048按384为片段划分，末段128，分区各自FDA16累积，再以FP32按0至5顺序相加，最后回BF16。原单路方法在完整148×768 gate/up分别有61/99个BF16差异；修正后两矩阵227328元素均逐位一致。相邻树归约在gate仍有4个差异，BF16工作区候选也失败，全部保留。

原失败64×2048 FFN分块复核：4差异降为0，目标GPU0。该复核是给定已证明正确FFN输入的隔离诊断，不是完整自主单层通过。

原始依据：review/FFN_FAILURE_DIAGNOSTIC.json、review/EXTERNAL_FFN_FAILURE_RESULT.json、review/SILU_DOMAIN_RESULT.json、SPLITK6_CPU_RESULT.json、FFN_REPAIR_V2_RESULT.json，以及原v4/expert28_trace.json。

## 为什么改为两阶段

收集了249种实际批量、两个矩阵形状共498项源核配置，8个核族；其中M142/148的gate/up为上述6路split-K。目录主要是无模型数值的形状探针，不能把498项配置采集写成498项数值PASS；目前完整小批量数值验证为M148。M142的同核方式仍须经过后续全层门。

原逐64查询块立即执行专家的方法不能自主得到原完整dispatch的专家批量。新流程先完成全部查询的attention和FFN输入，再由这些自主生成的完整FFN输入计算router和真实专家批量，按(M,N,K)选择已登记的CPU累积方式。不得用采集路由或源专家counts作为目标运行输入；未知矩阵形状显式拒绝。

第一阶段复用旧11776行中已校SHA并对原Golden复核的attention/FFN输入；旧专家输出不被新第二阶段直接复用。1660项断点/数值检查及4项新负对照通过。完整K/V和原输入仍沿用v4已验收资产，未降低文本/视频上下文。

## 正在执行的范围

113独立后台：同一已见layer0/step0，两CFG共98869行，全部真实K/V。最多16 CPU线程、nice10，数值任务最长12小时；无新增GPU、目标模拟器或物理NPU运行。按块/专家保存断点，数值差异、未知形状、异常退出或超时均保留现场并停止。数值完成后独立重载全部候选/原Golden，核对覆盖、成员SHA及路由；Unix other读/遍历模式在收尾核对，不冒充跨账号实测。

当前进度快照见STAGEWISE_PROGRESS_SNAPSHOT.json；快照不是实时状态。实时入口为：
/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4/full_layer_stagewise_v1/STATUS.json

日志：同目录上级stagewise_layer.log；最终独立验收：full_layer_stagewise_v1/INDEPENDENT_AUDIT.json。不依赖本机持续开机或SSH连接。

本轮3次有界外部GPU原语/子模块参考，完整模型调用0；v4加本轮为10次外部参考任务。新目标原生0，LingBot历史原生累计仍为旧片段1，物理NPU0。原16GiB EX2与64MiB RSQ host兼容表及保守容量预算不变，新增SiLU域表只作诊断；host/HB/NoC时序和HiBand/Sem-MoE收益仍未认证。即使本开发样例完整单层通过，也不等于48层40步、VLM/VAE或TI2V端到端通过。

## 交付与授权记录

先前源码上传两次自动审批超时，未作不安全判定，未执行该上传。随后用户明确批准3882B诊断包上传及限定外部GPU/CPU诊断；包SHA为df01b101387176c7d326cdae0717d25a2631cc24ea18650fe2e53e2e04f9404f，已上传校验并执行。后续CPU两阶段包通过工具审批，当前没有待用户审批的操作。

本地compact review共41份载荷、8396965 B，归档3931657 B，已与113提供的归档SHA逐位核对：0e04dc07569ea9030a7b5c2d83a4489c6c84fc50eabec6a4798a13117a7d5f3c。旧失败、修复输出与候选、源小批量参考和当前代码均保留；大型数学表、权重及全量查询输出留113，未声称全量回传。详见LOCAL_VERIFICATION.json和REVIEW_MANIFEST.json。

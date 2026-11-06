# 完整两层统一工具链续作

固定原BF16、128 GiB host＋8 GiB HB；目标GPU0，无新GPU采集、SWE或留出任务。当前为一个活动NPU/HB512 MiB的诊断子合同，不是全16节点运行。

## 后续修订（22时后）

原完整156105条PopNet回放及独立审计/归档已结束，113载荷本地SHA通过。但随后确认CPU原生2.5GHz tick与DRAM1.25ns周期的换算问题，旧运行只保留有限数值/载荷证据，不晋级目标时序。已隔离修复并通过16节点两轮时钟复验：381载荷本地SHA、每轮11296时钟观测和816条NoC反馈通过。完整层16节点时钟修订版正在运行，已核对prefill层0的14阶段；1—7仍PARTIAL。当前依据[时钟与16节点续作报告](../swe_qwen3_legosim_clock_fix_20261030_v1/REPORT.md)，下列运行中描述保留为早期快照。

## 最新已核实状态（16:37后）

FIFO修复版phase1已实际结束，CPU、NPU、DRAM三个子进程均exit0；CPU收到并逐字节核对prefill/decode两个完整层1结果，CPU_PASS回执存在且无EOF。远端PHASE1_AUDIT及本地LOCAL_PHASE1_V2_AUDIT通过：56阶段、12严格输出/KV、759权重版本、2998节点及7负对照。本地98个修复版载荷SHA通过，审查包4501751 B，SHA256为44e6b08cbe1d952b938199d154f19a97537fbc969f2e272fd526bc918e78b84b。证据位于unified_layers_review/unified_layers_fifo_v2和LOCAL_PHASE1_V2_AUDIT.json。

PopNet phase2于16:37:19启动，156105条完整通信记录仍在回放；未完成，不标完整反馈或目标时序通过。已启动有时限的监督/独立审计/归档程序，最终远端状态见unified_layers_fifo_v2/DELIVERY_STATUS.json。下文“重跑中”保留为修复前后过程记录，以本段核实状态为准。

## 已实际执行

已将R0002的19-token prefill和1-token cached decode、连续层0/1接入真实InterChiplet入口：Sniper CPU发送原输入，NPUSim ChipletNpuRuntime管理张量和算子事件，外部Ramulator承载实际BF16权重和中间张量，PopNet回放通信。

首轮56阶段文件与既有两层CPU参考逐字节一致；12项完整层输出/KV严格比较通过。759次矩阵调用均在同一32 MiB权重槽内先写权重再按tile读取；2998个不可变活动缓冲节点，HB地址上界63476832 B。所有缓冲保留至结束，尚未认证动态淘汰或复用分配器。SRAM检查只是静态工作集上界，不是原生SRAM分配/Bank仲裁认证。

首轮156105条bench记录已由原PopNet完整生成156105条delay，四个模拟器子进程均exit0。但CPU日志明确出现decode接收EOF，缺少decode_ACTUAL.bin和CPU_PASS.json，故首轮不能标端到端通过。Sniper外层exit0没有传播本例应用失败。

## 已定位与修复

NPU发送函数每条消息后关闭FIFO写端，而Sniper复用读端；两次消息之间会观察到EOF。新隔离目录unified_layers_fifo_v2把写端保持至进程结束，并修正decode输入节点的layer标签。原源码、原运行及EOF日志保持。

修复版在run3实际重跑。此前本版run1的参数错误、run2缺SIMULATOR_ROOT均保留，未产生数值运行。新验收必须同时有CPU双输出、CPU_PASS回执、56阶段SHA、12项严格比较、完整delay记录数；不能只依赖外层退出码。phase2_receipt_gate.py已确认拒绝原EOF用例，当前监督程序会再次审计实际结果。完成后的远端回执为unified_layers_fifo_v2/DELIVERY_STATUS.json；状态尚需读取核实，不因启动即视为成功。

## 独立审查与架构缺口

本地114个审查载荷SHA通过。LOCAL_STAGE_AUDIT.json确认上述阶段、权重字节流和已记录依赖；HB地址重叠、读早于就绪、非因果父节点、HB越界、权重长度破坏、SRAM静态上界破坏、权重last-reader之前覆盖七项负对照被拒绝。它明确保留CPU验收失败。

TRACE_DOMAIN_AUDIT.json将全部原trace分账，未删除记录：CPU/NPU激活4条，诊断HB RPC156101条。规范V3.6规定Ni↔CHi纵向链路与水平PopNet分离，因此这条三端点诊断回放不能认证规范架构的完整时序。HB实际payload3442522844 B；按128 B/5周期推导的134473549周期仅为串行吞吐占用下界，不是实测总耗时或固定延迟。

当前依赖图仍有1680个零父节点，其中包含布局/常量、cast、gather、路由归一化和KV发布等。串行执行及不可变保留避免当前用例的提前复用，但不能据此宣称显式数据DAG完整或允许异步重排。

GPU对照差异未变：prefill层0输出4249元素、路由10槽位；decode两项无差异。GPU GEMM与softmax FP32差异仍保留，无放宽容差或单输出补丁。

## 剩余出口

1. 取得修复版CPU双输出及完整NoC结束回执，独立审计并回传审查包；随后在同合同内验证完整层的delay反馈，而不是用旧残差norm反馈替代。
2. 按规范分离HB纵向服务、CPU PCIe/gateway与水平NoC，实际绑定16×512 MiB HB；当前拓扑不晋级V3.6完整认证。
3. 补足完整61GB权重host后备、搬运及CPU codec/SLEEF/控制/布局服务的统一计时。当前权重由NPU功能进程载入，host侧DRAM/PCIe ingress成本未完整进入模拟时间。
4. 补齐逐算子lowering、显式数据父依赖、实际SRAM驻留和last-reader释放机制。现有GEMM等使用通用FP32 vector/reduce服务代理，不能按原生BF16阵列吞吐解释。

因此第1—7步仍PARTIAL，尚无完整系统性能或HiBand/Sem-MoE收益结论。

来源：unified_layers_review/unified_layers/RUN1.log、run1/proc_r1_p1_t0/cpu.log、case1/FILES.json、CHECKS.json、NODES.json、MATRIX_CALLS.json及实际DRAM事务CSV；unified_layers_review/LOCAL_STAGE_AUDIT.json、TRACE_DOMAIN_AUDIT.json；whisper_operator_inventory/target_architecture_v3_6/target_architecture_v3_6.yaml。


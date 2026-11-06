# 完整两层16节点联仿：时钟修订候选

状态：RUNNING，不能标1—7步完成。2026-10-30 22:23在113实际启动；原BF16、128 GiB host＋8 GiB HB、目标GPU0保持。没有新GPU、SWE/agent或隐藏测试。

N0执行前半层、attention/KV、router与合并；专家矩阵按expert_id mod16放到对应NPU。全部模型参数由Sniper CPU从原checkpoint实际读取，经PCIe/gateway/XY NoC供给；功能参考副本不充当设备权重字节。这里使用阻塞、经host中转的通信基线，没有策略优化或并行收益主张。

第一轮完整prefill两层及cached decode两层已经执行完成：56阶段文件与冻结CPU源参考逐字节一致，12输出/KV及CPU双回传通过。759次矩阵、450次远端专家矩阵、61次host参数fetch已实际完成并逐RPC核对；160载荷本地SHA及433510条时钟观测通过，见LOCAL_PHASE1_AUDIT.json。phase1包另补取FREEZE.json冻结索引后通过完整本地检查，原包保持不变。

截至23:18，两轮phase1均已达到每轮759次矩阵、450次远端专家矩阵、61次host参数fetch，56阶段/12输出KV与CPU双回传通过。冻结输入为R0002同源prefill19和cached decode1、连续层0/1。第一轮全部28316条水平PopNet记录已通过，第二轮回放仍在进行；完整两轮独立审计未结束前不晋级。

CPU进程clock_rate=2.5，将0.4ns的Sniper全局tick归一到1ns；NPU/gateway/NoC仍为1。Ramulator.run返回DRAM周期，服务器以1.25ns换算；服务ready与接收tick向上取整。16节点独立前置用例已经两轮通过并完成381载荷本地SHA、每轮11296条时钟观测，见../swe_qwen3_legosim_16_service_20261030_v2/LOCAL_CLOCK_AUDIT.json。

原单NPU及16节点首版数值证据保留，但旧CPU clock_rate=1/DRAM scale=1.0的时序不晋级。完整候选v1的缺冻结清单启动失败、v2因时钟问题主动停止均保留。对原GPU的GEMM/softmax FP32差异、prefill输出4249与路由10槽位差异不撤销。

run_full.py有三小时运行上限，任一子进程失败即停。collect_independent.py为独立后台只读审计/归档器，不重启数值实验；完成后检查INDEPENDENT_AUDIT.json、CLOCK_AUDIT.json、COMPLETE_DELIVERY.json或COLLECTOR_FAILURE.txt。没有最终回执即没有通过结论。

## 仍未完成

完整算子及BF16 codec的合法lowering与CPU软件服务成本、实际SRAM驻留/8 Bank仲裁、完整显式DAG和异步释放仍需补齐。现有通用FP32 vector/reduce成本为代理，不能当BF16原生阵列吞吐。LPDDR5是研究服务代理，HB固定电气延迟未知；不能由本用例推导完整物理时序或HiBand/Sem-MoE收益。

来源：PROTOCOL.json、FREEZE.json、EXPECTED.json、CLOCK_BINDING.json、CLOCK_AMENDMENT.json、实际RUN.log与case目录；汇总见../swe_qwen3_legosim_clock_fix_20261030_v1/REPORT.md。

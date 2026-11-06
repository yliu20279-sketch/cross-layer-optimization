# v8 阶段状态隔离修复

2026-11-05 北京时间22:25核对。远端目录 `/mnt/sda1/h3240101068/swe_qwen3_lifetime_owned_20261105_v8_phasefix`。

CPU替身在接收阶段输入时显式设置 layer=0，与原生base_adapter一致。合同失配现在报告实际和计划完整五字段。由原始已见有限DAG重新生成3920节点计划，仅节点3133的layer从1改为0，其他字段及读者数不变。原目录、原计划和失败日志保留。

阶段回归执行真实receive_input方法，传输及张量由测试替身提供，prefill与decode均验证五字段。完整CPU两层回放及独立持有权审计通过3920分配回收、56阶段、12严格输出/KV、759 FP32投影、16持有权事件。实际3920节点及读者数逐项匹配新计划。证据见本目录PLAN_DIFF.json、PHASE_SWITCH_REGRESSION.json、OBSERVED_PLAN_AUDIT.json、OWNED_CONTROL_AUDIT.json。

控制脚本首次因Python3.8不支持dict合并运算符停止，失败回执留在新目录。独立resume脚本使用已完成CPU产物继续核验，没有重跑CPU。外部依赖SHA核验通过后更新冻结，22:24:55启动完整16节点两轮，PID2310999，nice10，36小时监管上限。数值、缓存、ISA、时钟、持有权、独立归档沿用严格门控。PHASEFIX_STATUS.json和RUN_PID.json为启动快照，非最终验收。

原BF16、host128GiB/HB8GiB、GPU差异和步骤1—7 PARTIAL边界保持。新原生运行仍待最终结果。本地取回小型回执和计划，未取回大型数值载荷或重算原始CPU日志。

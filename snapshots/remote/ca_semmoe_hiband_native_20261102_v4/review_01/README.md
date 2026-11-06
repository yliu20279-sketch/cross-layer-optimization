# Qwen3／Qwen1.5 P0接入续作 v4

先读[REPORT.md](REPORT.md)与[STATUS.json](STATUS.json)。P0-1b仍PARTIAL；P0-1c完成身份门控复用判定。正式性能实验0，P0-2未启动。

两模型实际CPU MoE载荷与真实Ramulator/PopNet控制分别有限通过，但尚未在完整目标层中耦合。CPU动态库不是NPU实现，主机copy不是目标NoC，不能将两条路径拼成完整系统性能结果。

- [新版两模型计划](../CA_两模型实验计划_20261102_v4.md)
- [20项实现账本](IMPLEMENTATION_STATUS_v4.csv)
- [132项旧结果复用判定](REUSE_DECISIONS.csv)：125个Q15运行＋7个Q3摘要，0项周期晋级。
- [113最终28项检查](evidence/REMOTE_SOFTWARE_CHECKS_v4.json)
- [最终CPU功能检查](evidence/REMOTE_PAYLOAD_AUDIT_v2.json)
- [真实后端控制](evidence/REAL_CONTROL_PROBE_02.json)
- [本地原始日志复核](evidence/LOCAL_CONTROL_AUDIT.json)

继承的v3 evidence/contract文件只保留原范围；当前状态以STATUS和contracts/gates.json为准。工具不应批量全运行：部分构建/探针工具有副作用及“输出已存在即拒绝”保护，按报告的具体入口使用。

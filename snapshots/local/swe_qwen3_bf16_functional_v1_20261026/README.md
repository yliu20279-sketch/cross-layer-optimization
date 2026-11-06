# swe_qwen3 BF16功能适配器 v1

当前状态：PASS_LIMITED_CPU_SYNTHETIC_SOURCE_SEMANTICS，51项检查0失败。仅CPU、合成算子/子链与固定原函数同backend比较；不涉及checkpoint、完整层/模型、GPU、目标时序或SWE任务。

- [报告](REPORT.md)
- [逐算子语义合同](NUMERIC_CONTRACT.md)
- [机器合同](OP_DTYPE_AND_ROUNDING_CONTRACT.json)
- [功能适配器](bf16_adapter.py)
- [实际CPU检查结果](attempt1/RESULTS.json)
- [运行前协议](RUN_PROTOCOL.json)与[编译/运行回执](ATTEMPT1_RECEIPT.json)

模型BF16、host128 GiB/HB8 GiB约束不变；原执行器/共享环境未改。完整源码对照与codec绑定见SOURCE_BINDINGS.json。后续真实GPUfixture与设备时序需分别验收，不从本轮PASS外推。

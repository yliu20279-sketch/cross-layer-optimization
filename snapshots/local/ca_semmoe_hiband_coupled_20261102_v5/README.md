# 两模型P0-1b v5

先读[报告](REPORT.md)及[状态](STATUS.json)。本轮新增同状态完整层、真实权重页搬移、独立官方CPU对照和原日志审计；仍PARTIAL，无正式性能运行。

- Qwen3 BF16：层0 TP16/EP16，prefill1＋cached decode1。
- Qwen1.5 Chat-GPTQ解码FP16：层0 TP4/EP4，修正TopK不归一化及FP16累加路径。
- 两模型均在prefill后固定交换8KiB权重页，实际迁移后decode走新地址；不是训练得到的CA布局。
- 当前驱动串行，CPU/PCIe/缓存成本未闭合；官方CPU对照仍有差异。不能用来作SOTA或净收益主表。

核心文件：`core/coupled_layer.py`、`core/coupled_backend.py`、`runtime/coupled_backend.cpp`、`runtime/coupled_matrix.h`、`core/coupled_decoder.py`。

原日志摘要、二进制小载荷与审计在`remote_review/`。大事件日志、权重与可执行文件留113，路径/SHA见审查索引。已有工具含写入/构建/运行副作用，不应批量执行整个tools目录；正式性能入口未提供。

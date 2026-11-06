# swe_qwen3：可移植CPU路径重跑

2026-11-02，RUNNING / PARTIAL，非最终验收。

v5因CPU ISA计费准入缺口主动停止，非已观察到的数值失败。只查主ELF的AVX指令不足以约束glibc动态选择。本隔离版使用实际SIFT/XED Nehalem准入计数、glibc Usable特征限制、ROI前显式动态绑定和进程级固定地址；不修改全机ASLR或公共模拟器。

代表性原生控制中5841条解码记录准入、零拒绝，VXORPS负对照被检测；该结果仅限探针，不替代完整两层最终ISA审计。两次固定地址控制相同，完整两轮仍要求缓存门控地址序列严格一致。

真实16节点完整两层重跑进程2476260已核对存活。实时前缀见LIVE_CACHE_PROGRESS.json；该文件是非最终快照。当前尚无整轮最终数值/ISA/缓存/PopNet/独立归档验收，36小时是监管上限，不是ETA。

原BF16、host128 GiB/HB8 GiB、GPU GEMM和softmax FP32差异保持。1—7仍PARTIAL；无新增GPU/SWE/物理或策略收益结论。

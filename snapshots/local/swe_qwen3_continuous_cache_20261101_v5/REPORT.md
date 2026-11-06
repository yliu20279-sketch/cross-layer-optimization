# swe_qwen3 v5停止说明

2026-11-02状态：STOP_AMENDMENT_CPU_ISA_PORTABILITY。

实际动态库分派中出现超出Nehalem计费准入的指令，主ELF零AVX检查不足以保证整条CPU服务路径。已停止本轮，转隔离v7可移植路径重跑。停止前127个FP32投影前缀核对一致；未观察到数值失败，不将未完成实验写成通过。

原始日志、失败和停止回执保留，见STOP_AMENDMENT.json。原BF16及host128 GiB/HB8 GiB不变。1—7仍PARTIAL。

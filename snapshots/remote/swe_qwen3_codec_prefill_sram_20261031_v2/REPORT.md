# 真实prefill专家16完整M6批量

2026-10-31，PASS_LIMITED；整体1—7步仍PARTIAL。沿用原BF16、host128 GiB＋HB8 GiB、目标GPU0，保留原GPU差异。

原prefill19的专家16实际接收token `[0,2,11,14,16,18]`，输入来自冻结`prefill_L0_post_attention_norm.bin`，K2048/N768、原checkpoint gate权重。未重跑模型/GPU/SWE，不把单token重复当成真实批量。

真实Sniper CPU在ROI内展开1585152个BF16元素，返回后执行4608元素BF16 RNE。实际FP32临时数据经PCIe/NoC/HB进入真实4 MiB SRAM；设备按原CPU源768/768/512 K分块、奇数后偶数顺序执行16-lane乘加，保留块间顺序。此核显式只覆盖该M6几何，不回退到通用未计费GEMM。

两轮各4608个FP32与未改C源逐位一致，4608个BF16与原CPU参考逐位一致。[本地独立NumPy复算](LOCAL_NUMERIC_AUDIT.json)再次按源顺序重算全部输出。CPU展开字节及恢复BF16的SHA与原始输入/权重绑定通过。

每轮9437184次FP32乘法、9446400次加法，共1180224条16-lane计算事件/周期；Bank服务10792872周期、12次权重tile版本、288组16输出last-reader记录。每轮148条水平PopNet、2452时钟观测，第二轮实际用第一轮delay；两轮共10子进程状态0。79.6秒为113联仿墙钟，不是物理负载时间。

Bank采用显式32 B条带/每Bank单共享读写端口研究配置，未改变原规范；3项冲突挑战和2项拒绝控制通过。当前矩阵布局引起集中Bank访问，这是该实现的资源成本，不是架构性能或策略收益。

142载荷归档6272889 B，SHA256 `259943585ae154d81ea8f4a071d4ab602fbf64b4d31f788c9db40d11b6f3f919`，[本地全成员SHA](LOCAL_ARCHIVE_AUDIT.json)通过。原始生产结果和源码见review同名目录，归档未改。

边界：单活动NPU0/512 MiB HB、单个真实专家gate，不是完整prefill层的成本覆盖；CPU缓存维护时序尚未认证，完整层仍未迁入此lowering。下一项必须迁入其余真实矩阵形状和软件算子，再回归连续两层；完整DAG/异步释放、物理校准及策略收益仍未通过。详见[续作总报告](../swe_qwen3_codec_fp32_sram_20261031_v1/REPORT.md)。

# LingBot TI2V 可行性与当前边界
日期：2026-10-26（Asia/Shanghai）。状态：READONLY_AUDIT_COMPLETE / INFERENCE_NOT_RUN。

已确认：固定源码 dd5c231e793406c6a8893e9e4307008a9c2adfe4 可下载，GitHub master API本轮返回同一SHA；固定权重修订 f2e538f64afe00cc4ae674db2aeb52e2945edfd5 的配置与索引可访问。仅下载小型源码、元数据和官方首帧样例，没有下载权重。来源URL、文件大小、SHA256见 SOURCE_MANIFEST.json。
配置48层、128 routed experts、Top8、1 shared expert；基础DiT索引 total_size=60272785536 B（约56.13 GiB）。这不含文本编码器、VAE、激活、内核工作区或加载临时副本；也不代表完整模型下载总量。
公开模型支持视频生成；本轮不认证动作条件机器人闭环。

本地：RTX4060 Laptop 8188MiB，当前Python无torch/diffusers/transformers；C盘可用约53.14GB，小于基础DiT索引载荷，不适合本地完整下载运行。D盘空间并非本任务可写授权目录。
113首次只读SSH工具回执：SERVER-113，2×H100 PCIe，各81559MiB总显存、81068MiB空闲，利用率0%；驱动570.133.07。RAM总270079823872B、available255610564608B；根分区available659091005440B。默认Python环境包路径为python3.8，torch2.4.1、transformers4.46.3、accelerate1.0.1、safetensors0.5.3；pip show未列出diffusers。此为工具首轮现场快照，非资源预留。
后续为保存同样回执重连时SSH别名无法解析，失败记录见REMOTE_READONLY_INVENTORY.txt。不能把初次连通写成当前持续可访问。上述首轮数据为工具回执转录，未伪称远端生成的原始文件。远端模型缓存、其他隔离环境、互联拓扑和compat库尚未查完，不能断言服务器完全无权重或无兼容环境。

依赖缺口：固定requirements推荐Python>=3.10，torch2.12.0.dev20260220+cu130、torchvision0.26.0.dev20260220+cu130、diffusers0.39.0、transformers5.8.1；默认环境不满足。NVIDIA CUDA13普通minor兼容路径要求R580+，当前R570需核验forward compatibility包或另选经验证的CUDA12环境，不擅自升级共享驱动。https://docs.nvidia.com/deploy/cuda-compatibility/forward-compatibility.html 和 https://docs.nvidia.com/cuda/archive/13.0.0/cuda-toolkit-release-notes/ 。源码依赖torch._grouped_mm，不能假定旧torch可直接执行。
固定源码的官方performance_benchmark报告单卡MoE90.15GiB峰值、CP8+DiT-FSDP8为37.61GiB/GPU；这均为480×832、121帧、40步T2V作者结果，不是本轮TI2V实测，不认证两卡配置。两卡总显存不能简单合并作单卡可用空间。FSDP2是待适配方案；不照搬CP8、不承诺显存或延迟。

结论：真实路由入口存在，最小TI2V在113的可执行性尚未确认。优先解决连通性、独立环境及两卡/单卡内存方案，再考虑选择性权重下载和单样本功能运行；当前没有推理、训练、算子回放、耦合仿真或策略收益结果。

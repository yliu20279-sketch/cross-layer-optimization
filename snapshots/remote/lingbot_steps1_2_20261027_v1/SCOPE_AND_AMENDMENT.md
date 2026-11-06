# 步骤1—2执行范围与参考环境修订

用户授权完成步骤1—2，并明确目标架构没有GPU。目标GPU数量固定为0；113物理GPU1仅为外部Golden参考设备，GPU0的其他用户进程不触碰。源GPU秒不转成目标NPU周期。目标V3.6原文件不改，选择host128GiB容量overlay＋HB8GiB只读共享cache，原BF16/F32模型及其舍入边界保留；不存在目标GPU fallback。

目标原语合同采用显式FP32 vector软件矩阵/CPU特殊函数回退候选，所有CPU/PCIe/gateway/HB数据依赖另计。此阶段冻结合同与容量分区、检查标量BF16 codec，不宣称完整LingBot BF16内核或时序认证；矩阵归约顺序、TopK、非线性、完整活跃集在真实fixture阶段继续验收。单次64立方tile的输入/权重/FP32展开/累加/输出仅73728B，低于4MiB SRAM；不是完整运行峰值证明。

独立venv位于113本用户lingbot_steps1_2_20261027_v1，复用只读Torch2.6+cu124基础包，新增Transformers5.8.1、Diffusers0.39.0等仅写入新venv。推荐Torch2.12nightlycu130与113R570普通驱动路径不兼容，未改系统驱动、未用共享pip升级。原源码提供torch._grouped_mm缺失时的逐专家for-loop分支；参考使用该原有分支，及原有chunked_scatter128降低临时workspace。attention为_native_flash。该参考变体不是作者nightly性能数字复现，未证明不同backend逐位等价。

参考采用分阶段模块驻留：文本编码器在GPU得到正/负条件后退回CPU；原FP32权重VAE在GPU按源encode autocast采样，保存随后generator状态；移回CPU；DiT在GPU做1步与40步，保持seed42、121帧、480×832、CFG3、shift3、FlowUniPC；结束后DiT移回CPU，原VAE在GPU按源decode dtype解码。相同条件缓存与RNG状态绑定保存，既不改checkpoint也不把目标CPU fallback解释为GPU执行。

1步是功能诊断，成功才40步；单worker最多90分钟，保存失败，异常不自动降帧、改dtype、增卡或安装共享CUDA。最终以REFERENCE_RUNS/FINAL_REFERENCE及输出文件校验为准；未产生完整回执前不称步骤2通过。

# 步骤4最终latent到VAE及输出帧有限验收

2026-11-05。状态PASS_LIMITED_FROZEN_LATENT_VAE_OUTPUT。

注入点为example_4原40步推理保存的最终DiT latent。加载前按旧REFERENCE_RUNS.json核对原始FP32字节SHA，形状[1,16,31,60,104]，值有限。后续使用原pipeline的DiT→VAE均值/标准差转换、原AutoencoderKLWan FP32解码、clamp/归一化及帧排列。基础TI2V、refiner关闭。没有将步骤3单层输出称作此处最终latent。

输出121×480×832×3个float32值，有限且范围[0,1]，24fps。首帧按原round-to-U8路径生成PNG，像素与旧first_output_frame.png全部一致。新导出视频与旧reference_40step.mp4逐帧解码，121帧均形状、顺序和RGB像素完全一致。原全量浮点帧没有保存，因此压缩视频帧一致不提升为旧全量浮点帧逐位一致。此次保留frames_FP32.npy和121项原始浮点帧SHA作为后续参考。

一次外部GPU1 VAE解码，目标GPU0，无新增Transformer前向；耗时约37.76秒，峰值已分配显存8924743168B。这是参考GPU功能边界回放；目标NPU VAE lowering、CPU/PCIe/缓存/通信完整成本及TI2V完整目标时序待验，完整系统仍PARTIAL。本次没有正式PK或CA消融。

证据只保存在113的本目录。入口为VAE_AUDIT.json、INDEPENDENT_OUTPUT_AUDIT.json、INPUT_BINDING.json、FRAME_MANIFEST.json、VIDEO_FRAME_COMPARISON.json、MANIFEST.json和DELIVERY.json。原始最终latent及旧输出原地保留，引用及SHA见INPUT_BINDING.json。原始浮点输出、新视频、首帧及代码收录evidence.tar。独立输出复核重新读取npy、逐帧核对SHA、重验首帧像素及逐帧比较回执，包内所有载荷再重算SHA。

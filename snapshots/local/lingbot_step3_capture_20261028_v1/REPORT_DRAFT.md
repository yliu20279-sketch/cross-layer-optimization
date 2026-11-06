# LingBot 基础 TI2V：步骤3真实路由与单层 Golden

步骤编号沿用七步摘要：本轮为真实路由/fixture采集，完整目标功能适配属于步骤4。目标架构没有GPU；本轮GPU仅生成外部源码参考，不能充当目标硬件。最终状态和数字以独立审计及本地交付回执补齐。

## 固定方法与运行范围

[PROTOCOL.json](PROTOCOL.json)、[FREEZE.json](FREEZE.json)在采集前冻结。源码dd5c231e793406c6a8893e9e4307008a9c2adfe4，权重f2e538f64afe00cc4ae674db2aeb52e2945edfd5；官方example_4、seed42、121帧480×832、CFG3、shift3、原混合BF16/FP32，排除refiner。复用步骤1—2已核SHA的条件/RNG缓存，不重新生成条件；这是已见开发样例，不是留出或独立泛化样例。

外部参考只用113物理GPU1，Torch2.6cu124、source expert for-loop fallback、native_flash、chunked_scatter128；未改原模型源码。此版本不等同于作者推荐nightly的速度复现。先同进程1步off/on配对，再40步on；本次不重复VAE解码。

## 原始路由与 Golden 内容

直接捕获原router返回的expert IDs/weights以及实际dispatch参数，不以离线TopK替代。全部48层、40步、两CFG覆盖3840条，另1步probe96条，总3936条；共享专家同为3936条。IDs以uint16无损保存，权重以原BF16 raw uint16保存。router与dispatch权重只有逐位相等才共享同一载荷；实际稳定pack顺序以原排列/权重SHA和128专家counts绑定。source rank0/CP1、没有EP设备消息、无语义或CP padding，当前fallback不执行grouped_mm padding。

视频token48360；正条件序列1523、负条件626，joint长度49883/48986。trace中的text_tokens沿用源DiT变量名，包含VLM图像来源的条件表示，不能解读为纯自然语言词数；冻结协议的“rest real text”在此明确限定为条件序列。实际joint位置ID已保存，未声称采集VLM内部每个子模态token的来源映射。

预指定40步run的step0/layer0两CFG为完整Golden，共28张量：层输入/输出、attention输出、post-attention norm、FFN输入/输出、post-FFN norm、共享专家输出、FP32 router logits/scores/choice、rotary、temb6及sorted_positions。temb6在所有行相等时仅存原BF16一行和扩展shape，采集逐行检查、审计再排除正负零歧义；这是无损编码。其余层未采集完整logits或每个中间数组。

## 验收边界与后续

全量独立CPU审计只读取原始数据，不创建CUDA计算，不把CPU重算ID替代实际选择。结构检查覆盖ID范围/Top8唯一/finite、非负、BF16权重和2.5的舍入偏差、实际pack哈希、时步转换、位置布局、共享专家覆盖、fixture SHA/finite、源93文件Git blob及refiner排除。两份层0的FP32实际score另核correction bias、合法group-limited选择集合和无bias权重舍入界；这不是目标CPU/GPU router逐位数值认证。

首次审计直接比较scheduler时步与DiT实参，失败保留；源码先转BF16 sigma再乘1000，所以999实际成为1000。修订审计按原转换逐操作核对，不加容差；同时修复局部变量名遮蔽及temb原dtype为BF16而非FP32的审计假设，详见[AUDIT_REVISION.md](AUDIT_REVISION.md)。未改采集输入、输出、冻结方法或阈值。

本轮不证明目标BF16完整算子、HB/SRAM生命周期、CP/EP通信、CPU/PCIe/gateway时序、Bank或NoC关键路径、动态HiBand/Sem-MoE或净收益。host128/HB8仍为显式研究配置，原host8规范不改；目标GPU0、模拟器0、物理NPU0。下一步从已保存全上下文Golden的确定子合同做原精度功能适配，先数值门槛，再驻留/因果/时序；不要直接启动收益矩阵。

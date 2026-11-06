# LingBot 基础 TI2V：步骤3真实路由与单层 Golden

步骤编号沿用七步摘要：本轮为真实路由/fixture采集，完整目标功能适配属于步骤4。目标架构没有GPU；本轮GPU仅生成外部源码参考，不能充当目标硬件。步骤3采集和完整性验收已完成，状态PASS_LIMITED_REAL_ROUTE_CAPTURE_AND_FIXTURE_INTEGRITY；完整目标算子功能仍未认证。

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

## 最终机器回执与交付

[独立审计](server_evidence/INDEPENDENT_CAPTURE_AUDIT.json)：31568项检查0失败，六项原始数据负对照全部拒绝；3936条路由及3936条共享专家调用完整，完整40步3840条。逐项验证全部原始route文件，而非抽样。28个完整fixture张量通过SHA/finite检查。最大权重和偏差0.009033203125（阈值0.02）；有效权重为零的slot数0。token-layer出现次数为{"probe_on": 4745712, "full_on": 189828480}，不是独立样例数。

[运行回执](server_evidence/CAPTURE_RUNS.json)：同进程probe_off/on的raw FP32 latent SHA均为b536bc0141cdc00746830674b37aa817fa7cc9b3bdbf52162f48d8854e715784；40步raw SHA=109c7757fcff273a6625e8fa0dcf0fbf44dd4db9b21b893d7817ce69d7132c1f，与此前无采集40步参考一致。probe_off/on观测耗时分别16.424/17.207秒，40步on为720.220秒。这些时间含包装/保存，只是一对观测，不是普遍采集开销或目标延迟。

完整原始路由与Golden保留在113：/mnt/sda1/h3240101068/lingbot_step3_capture_20261028_v1。采集载荷9679536472 B；[远端完整成员SHA清单](server_evidence/REMOTE_FULL_FILE_MANIFEST.json)记录封包时4038成员、9733096629 B（含脚本/日志/元数据及review副本，非仅采集载荷）。层0权重不重复复制：[WEIGHT_REFERENCES.json](server_evidence/WEIGHT_REFERENCES.json)绑定canonical shard、tensor头部和此前完整权重校验SHA，本轮没有重算全模型69.69GB。

本地是明确标注的compact review包，不是全量回传：[LOCAL_VERIFICATION.json](LOCAL_VERIFICATION.json)核对外层SHA及72载荷成员、63625555 B；外层45135512 B，SHA256=9c69c5737876f0e15e90185ac5f6f422b596a182f8d6b2c04daf16db24c18ad8。包含全部路由元数据/全量成员SHA、原始三份latent、六份选定路由、26份Golden选定行副本及审计/失败/协议代码。review行来自完整上下文运行的前32视频行和最后32条件行，不是缩短输入后的模型输出；完整Golden留113。temb常量行整行保留；完整sorted_positions只在远端。

外部参考进程已退出，检查时两GPU均仅23MiB，无本轮模型占用；未操作其他用户进程。没有目标GPU/模拟器/物理NPU执行，也没有HiBand/Sem-MoE收益结论。

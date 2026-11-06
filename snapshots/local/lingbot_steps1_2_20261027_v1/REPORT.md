# LingBot步骤1—2：无GPU目标合同与外部参考功能验证

收尾核验：2026-10-28（Asia/Shanghai）。执行发生于10月27日，参考attempt2于21:04:05完成。状态分开记录：步骤1为PASS_LIMITED_CONTRACT_STATIC_BUDGET_AND_CPU_CODEC；步骤2为PASS_LIMITED_EXTERNAL_GPU_REFERENCE；目标NPU/模拟器运行0、目标GPU数量0。不能将这两项有限通过解释为完整BF16目标执行或HiBand/Sem-MoE收益通过。

## 用户要求与完成范围

用户要求完成“确定原精度/存储方案”和“官方参考功能验证”，并明确目标架构没有GPU。本轮未向目标加入GPU，未修改规范V3.6 YAML、共享模拟器或旧结果。113的物理GPU1只用于外部Golden生成设备；GPU0当时存在其他用户进程，未占用或干预。GPU1在参考程序退出后释放；28日核查没有残留本线参考进程。

步骤1完成了明确的目标资源/精度合同、host/HB静态分区、标量codec检查以及实际token尺寸下的候选容量账本；不是完整算子能力认证。步骤2完成了官方样例原权重/原精度的1步诊断和40步参考、latent/视频检查以及证据回收；不是目标架构执行、作者推荐环境性能复现或生成质量基准。

## 1. 无GPU目标的精度和存储合同

[TARGET_CONTRACT.json](TARGET_CONTRACT.json)选择显式研究配置host128GiB＋HB8GiB，总NPU16、每NPU SRAM4MiB，target_contains_gpu=false；原规范host8GiB与所有旧配置保持。完整原BF16/F32权重在host保留只读canonical副本，HB为共享cache，干净权重失效不回写D2H；latent、activation、scheduler等可变状态不能套免回写规则。

目标没有新增BF16阵列或GPU fallback。BF16矩阵候选为tile解码→显式FP32 vector乘加/归约→按源边界RNE写回；router/time MLP为FP32软件矩阵；特殊函数、TopK/scatter等先保留target host CPU软件回退，并要求后续把CPU、DMA、PCIe/gateway、HB/SRAM完成门控全部耦合。VAE卷积仍为软件/分块或CPU回退候选，未实现认证。不得套用FP16 2048 MAC/cycle到BF16或FP32，也未填入未经校准的cycles。

净张量69655987276 B作为host canonical预算，另预留系统8GiB、可变状态16GiB、fixture staging8GiB、runtime/页元数据4GiB，剩余约27.13GiB。每CH512MiB划分weight cache320MiB、activation工作区128MiB、DMA staging32MiB、runtime/metadata32MiB。此为分配上限和拒绝规则，不是所有实际活跃集已经证明可装入。

[TARGET_CONTRACT_VALIDATION.json](TARGET_CONTRACT_VALIDATION.json)记录10项CPU标量BF16 codec检查（含±0、RNE偶/奇平局、Inf、NaN、subnormal）通过；64³ tile的BF16输入/权重/输出＋FP32展开/累加合计73728B，小于4MiB SRAM。该检查不证明独立BF16 GEMM、源GPU归约顺序或目标时序已正确。

原TP16全joint hidden复制不适合直接按128MiB activation池常驻。为容量账本选择另一已登记候选CP16＋EP16：实际最大S=49883，pad到49888，每rank最多3118个sequence token，attention发送/接收QKV、双hidden、time modulation流式tile64和8MiB向量reserve的静态合计113704960 B，低于128MiB池。[MEMORY_ADMISSION_CANDIDATE.json](MEMORY_ADMISSION_CANDIDATE.json)明确这不是liveness认证，不能把TP和CP的两套通信量同时计入。

CP路径内部router_target_m可将局部FP32 router输入补到全局S；其额外padding算术和缓冲不能漏计。目标需stream/host staging或独立证明可消除，当前容量账本不等于CP完整router已经验收。全部source-sized temb6、restore unsorted或score矩阵也不能直接在每CH全物化；未来tile生成/流式合并需保留数值边界并过真实fixture门。

## 2. 外部参考环境及明确变体

参考根目录：/mnt/sda1/h3240101068/lingbot_steps1_2_20261027_v1。新venv以只读的qwen-moe-route基础Torch2.6.0+cu124构建，新增包仅装入新venv：Transformers5.8.1、Diffusers0.39.0、Accelerate1.15.0、Torchvision0.21.0、PEFT0.19.1；安装日志和pip freeze在[server_evidence](server_evidence)中。

固定源码推荐Torch2.12nightly/cu130与113 R570普通兼容路径有缺口，本轮未升级共享驱动，使用经导入/小型BF16探针通过的Torch2.6/cu124路径。torch._grouped_mm不存在时进入原源码已有的逐专家for-loop fallback；restore使用原有chunked_scatter、chunk128；attention为_native_flash。没有FP16、W4、FP8或checkpoint替换，没有下载或运行refiner。

这是原模块可用的参考变体，尚未和推荐nightly/grouped_mm/scatter环境逐位配对，不称作者环境或性能数字的复现。reference GPU seconds不用于目标NPU周期。分阶段驻留将text encoder、VAE、DiT分别放入外部GPU1，原CPU/模型dtype和forward未改；源条件encode autocast与后续FP32 VAE decode边界保留。

第一次参考因Diffusers在组件分阶段卸载后自动把执行设备识别为CPU，和CUDA RNG冲突，失败发生在生成初始latent之前。原run_reference.py、reference.log、REFERENCE_FAILURE.json全部保留。attempt2仅在参考包装器显式覆盖_execution_device=cuda:0（CUDA_VISIBLE_DEVICES=1映射的物理GPU1），复用第一次原编码器保存的条件和post-encode RNG状态，避免重复编码或改变随机序列；不改源forward和模型权重。见[修订范围](SCOPE_AND_AMENDMENT.md)、[attempt2修订](server_evidence/attempt2/AMENDMENT.json)。

## 3. 真实样例和功能结果

固定官方assets/cases/ti2v/example_4首帧＋JSON、seed42、480×832、121帧、CFG3、shift3、FlowUniPC。真实正条件1523 token、负条件626 token，video token48360，joint S分别49883/48986；cond_latent [1,16,1,60,104]。不把缩小尺寸或合成路由替代官方样例。来源：[CONDITION_SHAPES](server_evidence/CONDITION_SHAPES.json)。

| 参考阶段 | 实际DiT forward | latent shape | 检查结果 |
|---|---:|---|---|
| 1去噪步诊断 | 2（正/负CFG） | [1,16,31,60,104] FP32 | finite，保存/回读SHA一致 |
| 40去噪步参考 | 80（每步两分支） | [1,16,31,60,104] FP32 | finite，保存/回读SHA一致 |
| 最终VAE与视频 | 不新增DiT | [121,480,832,3] | 实际解码121帧、24fps |

加载dtype按头部独立复核：DiT参数F32 51874304元素、BF16 30032631872元素；另有6144个F32 correction-bias buffer，与原头部总元素差恰好对应。文本编码器4437815808元素全BF16，VAE126892531元素全F32。并非仅把配置字符串写成BF16。

40步参考包围的cached-condition pipeline调用及latent回传/保存约641.24秒；attempt2总wall约906.62秒，包含本次加载、1步诊断、40步、decode/输出，但不包含首次条件编码。参考峰值allocated约72.09GB。这些都是外部参考设备/包装器实测，不是目标模型延迟，也不是无缓存完整TI2V端到端性能。

产物：[参考视频](server_evidence/attempt2/reference_40step.mp4)、[首帧预览](server_evidence/attempt2/first_output_frame.png)、[1步/40步原始结果](server_evidence/attempt2/REFERENCE_RUNS.json)、[最终有限通过回执](server_evidence/attempt2/FINAL_REFERENCE.json)。已人工查看首帧，未进行动作、物理合理性、画质/时序一致性或统计生成质量评估。

## 4. 独立审计与本地交付

[INDEPENDENT_REFERENCE_AUDIT.json](server_evidence/INDEPENDENT_REFERENCE_AUDIT.json)包含25项CPU只读证据检查，0失败：两份latent形状/dtype/finite/raw SHA、实际2/80次forward、scheduler长度、层0/47边界82次、三个组件参数精度数量、93份固定源码Git blob未变、refiner不存在、视频实际解码帧数/大小/fps。审计没有重新运行模型或创建CUDA计算。

证据包39载荷、38993604 B；外层34385586 B、SHA256=cad026e7de05b9a8195ac859568ee186a23a2b0701afb6e31955d05df9c49656。外层及所有成员在本地逐SHA通过，见[LOCAL_VERIFICATION.json](LOCAL_VERIFICATION.json)。venv和69.69GB模型不重复入包；原条件、两份latent、视频、失败、代码/协议/环境和审计均保留。

## 5. 本轮尚未完成的事项

未做真实expert IDs/weights全量trace采集（只有forward边界计数），未实现或认证完整目标BF16/FP32算子、CPU回退的Sniper/PCIe/gateway耦合、host/HB在线pager、CP/EP设备通信、完整HB/SRAM生命周期及Bank仲裁；目标模拟器运行0、物理NPU运行0、策略收益0项。步骤1的静态上限不能替代这些执行门。

下一步是已完成参考上的真实router/dispatch与单层fixture采集及原精度功能适配，先小样本完整核验，再扩48层/40步；暂不进入HiBand＋Sem-MoE性能矩阵。任何后续目标结果仍必须保持“目标GPU0”，不得将本外部参考GPU当作目标特殊函数或卷积设备。

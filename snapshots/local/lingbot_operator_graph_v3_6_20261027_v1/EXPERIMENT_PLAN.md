# LingBot基础TI2V：HiBand＋Sem-MoE后续实验计划

日期：2026-10-27。状态：PLAN_ONLY_NOT_EXECUTED。本计划在算子/任务图之后制定，原BF16/FP32语义和base checkpoint保持，不下载refiner、不替换DMD/FP8/量化模型。咨询与源代码分歧以REPORT.md的核对为准。

## 目标和可声称的范围

目标分四层：官方GPU参考输出与真实路由 → 原精度算子/单层功能 → completion-driven NPUSim/Ramulator/PopNet目标片段 → 固定资源下HiBand和Sem-MoE的各自/组合净增量。不将GPU时长换成目标NPU周期；不将CPU功能函数＋事件门控称物理NPU执行；不将现有HiBand独立参考模型称作者完整artifact复现。Sem-MoE当前工程co-clustering是近似实现，论文模型/数据协同调度的合同须逐项标明已实现、近似、缺失。

原始依据：[咨询1](consultation_sem_moe_sota_1.md)、[咨询2](consultation_sem_moe_sota_2.md)、[HiBand当前状态](../hiband_reproduction/STATUS.md)、[Qwen1.5工程入口](../qwen1_5_moe_a2_7b_v3_6/README.md)、[Sem-MoE工程代码](../qwen1_5_moe_a2_7b_v3_6/sem_moe.py)。Sem-MoE论文原文链接见咨询2；本轮没有重新完整审计论文，不额外宣称原论文算法/数值复现。

## 阶段0：先冻结算子、精度和存储合同

输入为本目录REPORT/图/MAPPING/CAPACITY、冻结资产SHA。逐层/模块核对header shapes和dtype；保留source grouped padding、restore backend、time/modulation、joint video/text、VAE encode autocast等边界。把矩阵、reduce/vector、特殊函数、index/scatter、Conv3d/cache分别映射到可验证的软件原语或host fallback。

明确原V3.6没有BF16阵列认证，router是FP32 GEMM，VAE还有FP32卷积。不允许静默BF16→FP16替换或套FP16 MAC/cycle。候选软件分解可先做CPU合成微探针，但每个格式转换、乘加/求和顺序、搬移和目标原语开销另计；对原GPU数值的容差与选择边界先冻结。

容量必须先作选择：建议host128GiB只读完整后备＋HB8GiB cache，不改原规范host8；仅为待选overlay，完整模型/激活峰值仍需证据。另一选择为原host8＋显式外部存储，必须建真实服务路径。不能把“容量表正余量”当pager、DMA或BF16时序已通过。

交付：PRECISION_CONTRACT、STORAGE_PROFILE、原语支持/缺项、生命周期预算。精度无合法lowering或全组件后备无定义则停止在BLOCKED，不启动完整性能矩阵。

## 阶段1：隔离环境与最小真实GPU参考

重新只读查113当前两卡占用、host RAM、存储、NCCL拓扑、独立Conda环境与驱动。此前H10080GB×2是历史快照，不抢占其他聊天GPU作业。固定源码推荐Torch nightly cu130与R570普通兼容路径有缺口；查可用CUDA12环境或正式forward-compat方案，不改共享驱动/共享包。

每次环境候选另建目录，先import/API探针、BF16 GEMM、grouped_mm/其源fallback、attention backend和FSDP/CP兼容。推荐版本名不证明轮子可用。官方单卡90.15GiB是T2V作者结果，不能承诺80GB单卡TI2V能跑；FSDP2或受支持的offload为待验方案，不照搬CP8，显式计CPU加载副本。

冻结官方example_4首帧/JSON、负条件、seed42、480×832、121帧、CFG3、shift3、FlowUniPC、无refiner及全部backend开关。先1去噪步，两CFG分支、48层；此结果只作为加载/forward/结构fixture，不称常规视频质量或40步路由代表。若资源不满足，停止并修改协议后重试；不静默降分辨率、帧数、dtype。成功再完成一次40步开发参考，保存视频、latent/selected intermediates、实际timestep序列、解析参数、环境和命令/日志/峰值及SHA。

阶段1验收是参考可运行与输出有限性，不是NPU可执行或研究总体生成质量通过。不得把减步诊断输出当正式5秒质量样本。

## 阶段2：实际路由与fixture采集，控制采集开销

按REPORT第4节schema，在实际router返回和实际dispatch入口捕获，保存正/负分支、每step/layer、video/text、实际slot/权重、padding/CP/pack身份。保存一个预指定layer0/step0双分支的完整输入/权重引用/阶段Golden、边界TopK平局、router FP32 logits及共享专家输出；不是只留频数。

开关hook配对同输入seed，逐阶段比较latent/route/output；若不同定位同步/数值/重算问题，不宣称无扰动。文件按step/branch/layer分块，异步写入完成也必须留manifest；uint16ID+BF16权重纯视频下界约5.94GB/40步，完整每个FP32[S,128]数组约95GB，先冻磁盘预算。全logits/scores仅小样本全量、其余用可核验选中值/分组摘要；避免为省空间丢掉重验选择所需证据。

验收ID0..127、Top8互异、非负有限、有效权重和约2.5、实际padding/zero assignment守恒、48层/两CFG/实际steps与rank去重完整；shared和grouped padding另账。token对应按global joint位置及图像latent坐标绑定，不能把文本token省略。去噪步不可跨样本拆分成“独立留出”。

## 阶段3：原精度功能适配，从真实片段到完整DiT层

先用阶段2原fixture逐op核对router FP32 linear、sigmoid/bias/组选择、实际权重、RMSNorm/LayerNorm、RoPE、BF16专家/SiLU/乘法、restore-slot FP32 sum、shared、调制/残差。CPU源码与自身一致只证明功能适配；GPU或独立精度参考另比，TopK tie保留实际选择，不用热度近似判PASS。

再合并单层attention/MoE两条链，保留全joint文本/视频mask；验证非因果attention与packed样本隔离、post norms和最终输出头。完整条件编码器/VAE继续按源24vision/36text/Conv-cache分图核对；若仅DiT，则结果标题写DiT，不声称TI2V端到端。

首个目标原生片段先选router或专家一个真实tile，显式32B事务、SRAM生命周期、BF16 codec与目标FP32/software原语；随后单expert→MoE→完整block。所有目标事件必须阻塞消费者，数值由CPU执行时明确写CPU求值＋模拟器事件门控，物理NPU运行数保持0。

## 阶段4：固定通信合同与容量/因果验收

首选结构候选Attention-TP16＋EP16（MAPPING.json）。16 heads各rank1头，无GQA复制；O归约bias只加一次。origin/rank、expert owner、actual slot分开，dispatch/return各一次，shared每token仅在origin执行。源归约顺序和BF16边界须独立核对，不能任意rank预归约。

保留两个分开的比较分支：A为整样本Attention-DP＋EP16（带复制与HB分页账本），B为Attention-TP16＋EP16；源Ulysses CP作为B的替代实现单立合同，不能一张图叠加TP和CP流量。CFG并行也不等于DP重排训练样本。DP没有足够完整样本/内存时记录不可行，不造合成视频或拆视频token充数。

目标通信先固定模式：单layer/step/branch → 双CFG → 相邻2step → 48层 → 完整40step回放。每次验输入/输出/字节、n[o,r]、metadata、SRAM/CH峰值、host clean cache miss、PCIe/gateway时序、32B地址解码、消息/事务守恒和早释放负对照。复用旧Qwen基础设施只当接口参考，不能继承旧ABI、地址、W4、synthetic路由或速度。

## 阶段5：Sem-MoE画像与在线合法性

从完整开发视频样本建立层/step-band/CFG分开的expert affinity，同时保留video/text身份。固定像素位置不是跨视频“语义token”；若无法建立可复用feature/semantic key预测关联，纯position共现只叫position-profile策略，不称原Sem-MoE语义模型已复现。离线交替聚类与原ILP/启发式差异明确列出。

专家p_l(e)与token origin/scheduling分别优化，容量保持每rank8routed experts或相同字节约束，shared/router/attention映射相同。预测/布局只能用开发数据、当前已到达条件和已释放信息；本步实际route可在router完成后用于dispatch，但不能用未来step route提前搬页。当前完整轨迹事后优化只能作route-known oracle上界。

开发集与未读评估集按完整首帧/场景/视频来源隔离，同一视频不同step/CFG不跨集；freeze方法/预算/seeds/哈希后才访问评估，评估反馈调参须改称开发。在线语义预测不成立则不推广Sem-MoE部署收益，只报告可行固定布局/离线oracle。

## 阶段6：HiBand固定到动态的独立门

先验证HB/水平NoC流量分类和固定模式服务敏感性，再加入根据当前pending local/global bytes的动态控制，显式drain→setup/switch→buffer release及模式驻留。模式改变必须实际改变后端服务/争用并进入同一DAG，不是改标签、固定GLOBAL_BIAS或只画选择器。无作者完整artifact时称HiBand独立参考集成，不声称论文数字复现。

冷/暖起点、缓存驻留、HB read/write、NoC collective、PCIe、切换次数/时延、SRAM峰值和控制器开销逐项保存。NoC等待下降但makespan不变时不能判为净收益。绝对热须补HB几何/RC/功耗校准；旧32GiB Qwen热模型不能替代8GiB规范，当前不安排绝对热收益承诺。

## 阶段7：四组公平对照及Bank/NoC诊断

仅前述门通过才运行：B0固定合法placement＋固定HiBand；B1同placement＋动态HiBand；B2冻结Sem-MoE model/data scheduling＋与B0相同固定HiBand；B3相同Sem-MoE＋与B1相同动态HiBand。两因素2×2分别报告B1/B0、B2/B0、B3/B1、B3/B2及交互；不把全部差异归于其中一个机制。

四组相同输入/seed/完整trace、精度/数值合同、Attention分支、容量/数据摆放合法性、缓存初态、量化/元数据、调度预算、host后备及计费路径。先做固定轨迹回放评估目标策略，不称闭环在线生成；闭环需后续数值/质量配对，dispatch不改变原语义。

Bank研究在冻结expert→partition后只改partition内页Bank布局：original、RR、Heat、CA及匹配合法随机；相同候选池/改动页数/冷热约束/配对seed。NoC另做同义shadow/oracle关键路径对照，Bank/row/column变化分账。CoAccess画像不从评估未来route取边；没有可释放Bank关键路径空间就报告NO_PROMOTION，不套用Qwen自然块或人工压力收益。

主指标为完成本合同的总周期/请求完成时间，分开源GPU秒、目标代理周期、CPU/PCIe/gateway时长；同时报告overlap、bytes、cache/migration/switch/control costs、路由负载、覆盖率/失败。建议预登记净周期改善至少1%且覆盖profile/install/migration/control成本才晋级下一规模；这是拟定工程门槛，必须在性能运行前冻结，不声称统计显著性。随机与输入独立重复数量按资源先做成本估计，不自动启动完整矩阵。

## 可复用基础设施与禁止继承

复用路径：qwen1_5_moe_a2_7b_v3_6/build_workload.py、sem_moe.py、lower_legosim.py、validate.py；qwen3_30b_a3b_v3_6_experiment/tiered_pages.py与paging_preflight.py；其bank_conflict_v2的arrival/completion/normal-oracle审计；hiband_reproduction统一DAG/固定动态模式契约。读取并核对入口参数/源码哈希后适配新目录，不运行旧main覆盖原结果。

不继承：Qwen的自回归token身份/prefill/cached decode/teacher-forcing、GQA四份KV、EP4/Top4、24层60专家、256B execution overlay、W4权重、旧合成路由、旧32GiB绝对热、任何历史收益。

## 每阶段留存和停止条件

每阶段独立目录保存协议/修订、输入/模型/依赖/二进制SHA、精确命令/解析参数、seed、日志/退出码、shape/dtype/数据来源、失败、源与目标Golden、路由/地址/事务/消息清单、审计、原始结果及可复核报告。初始运行1worker、有界超时与预算；资源不足、精度/TopK/归约失败、容量无定义、32B ABI/回调守恒失败时停止晋级，保留现场。不得自动增卡、改dtype、补合成路由、训练或重启其他聊天作业。

本轮只交付阶段0前的结构与计划；未选择host overlay、未装依赖、未启动阶段1或性能矩阵。下一次执行应首先处理原精度/存储合同及独立环境，再运行一个明确预算的官方开发样例。

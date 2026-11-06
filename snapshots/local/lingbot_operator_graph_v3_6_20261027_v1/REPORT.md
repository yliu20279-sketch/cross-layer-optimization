# LingBot 基础TI2V：算子拆分、任务图与V3.6候选映射

日期：2026-10-27（Asia/Shanghai）。状态：STRUCTURAL_DELIVERY_ONLY；本轮只读源码/配置/权重头部并生成结构产物，没有加载模型求值、GPU推理、路由采集或目标模拟器运行。后续计划单列于[EXPERIMENT_PLAN.md](EXPERIMENT_PLAN.md)，不把计划写成已执行。

## 交付入口与范围

[图形总览](index.html)包括四张SVG及PNG：[TI2V任务图](01_pipeline.svg)、[DiT单层](02_dit_block.svg)、[MoE路径](03_moe.svg)、[目标映射](04_mapping.svg)。源算子见[OPERATOR_INVENTORY.csv](OPERATOR_INVENTORY.csv)，48层单forward图见[DIT_FORWARD_48.json](DIT_FORWARD_48.json)，40步请求模板见[REQUEST_40STEP_TEMPLATE.json](REQUEST_40STEP_TEMPLATE.json)。源码图与目标并行图分开；目标层完成依赖见[TARGET_LAYER_COMPLETION_GRAPH.json](TARGET_LAYER_COMPLETION_GRAPH.json)，映射及通信变量见[MAPPING.json](MAPPING.json)、[COMMUNICATION_LEDGER.json](COMMUNICATION_LEDGER.json)。

单forward是48层、2271个符号节点、2993边；每层47个节点，routed experts保留条件宏节点，未伪造128份实际kernel。请求图210节点/450边，将40个step的两CFG forward表示为调用宏，不能把它当210个实际kernel或实际采集DAG。目标图有条件的origin/owner通信边，未产生实际消息、地址或周期。结构审计结果见[STRUCTURAL_AUDIT.json](STRUCTURAL_AUDIT.json)。

条件编码器和VAE已拆到源模块、算子族、配置维度及权重头部层级，见[CONDITIONING_SCOPE.json](CONDITIONING_SCOPE.json)；尚不是每个卷积tile、时序cache chunk或依赖后端融合kernel的完全物化图。完整系统执行必须补齐这些分图，不能用DiT局部结果冒充端到端TI2V。

## 1. 源码、资产和方法咨询

LingBot源码固定dd5c231e793406c6a8893e9e4307008a9c2adfe4，模型固定f2e538f64afe00cc4ae674db2aeb52e2945edfd5。141文件69694390066 B的资产完整性/Unix权限验收已完成，refiner权重排除，见[下载完成报告](../lingbot_ti2v_feasibility_20261026_v1/DOWNLOAD_COMPLETE_20261027.md)。本轮不改变权重、原精度、旧协议或规范架构。

按用户明确要求，已向“聚焦 Sem-MoE SOTA”（01a08eeb-3a1a-7c83-b6a5-aa3d7edd7788）及“聚焦 Sem-MoE SOTA (2)”（01a0a386-9539-7682-952a-6da9963f9698）分别询问算子拆分和HiBand＋Sem-MoE经验，原回复保存为[咨询1](consultation_sem_moe_sota_1.md)、[咨询2](consultation_sem_moe_sota_2.md)。两者都是方法建议，不能代替源代码、真实fixture或独立执行证据。

采用建议：源语义图/逻辑通信图/硬件物化图分层；保留Attention-DP和Attention-TP/CP独立合同；真实router输出、shared、padding、CFG与去噪步分别记账；权重/网络完成后释放消费者；固定/动态HiBand分步验收，四组对照不改工作量。校正的咨询细节：咨询1“每NPU/HB partition 8GiB”是错误，规范是全机8GiB、每CH512MiB；咨询2将最终归一化写为RMSNorm，但源码实际是LayerNorm。源grouped_mm连空专家也对齐至少8槽，不把dummy算术从源码账本抹去。咨询原文保留，不静默改历史回复。

源码快照和SHA见[SOURCE_MANIFEST.json](SOURCE_MANIFEST.json)。额外依赖参考为官方Transformers v5.8.1 Qwen3-VL与Diffusers v0.39.0 Wan VAE源码，见source/UPSTREAM_DEPENDENCY_SOURCES.json；这是所推荐版本的静态参考，不是113已安装兼容性证据。出处：[LingBot固定提交](https://github.com/Robbyant/lingbot-video/tree/dd5c231e793406c6a8893e9e4307008a9c2adfe4)、[Qwen3-VL固定依赖源码](https://github.com/huggingface/transformers/blob/v5.8.1/src/transformers/models/qwen3_vl/modeling_qwen3_vl.py)、[Wan VAE固定依赖源码](https://github.com/huggingface/diffusers/blob/v0.39.0/src/diffusers/models/autoencoders/autoencoder_kl_wan.py)。

## 2. 应用任务拆分

基础TI2V为首帧图像＋结构化JSON到视频，不是机器人动作条件闭环，也不是自回归聊天模型。流程是：图像预处理 → Qwen3-VL正/负条件编码 → VAE图像编码和Gaussian采样 → 视频随机latent → 初始条件片覆写 → 去噪循环 → 最终VAE解码 → 后处理/视频文件。Qwen3-VL调用的是text_encoder.model输出hidden states，不执行LM head或生成文本；没有额外27B rewriter，也没有refiner。

每个去噪步对当前latent分别运行条件/无条件DiT，然后FP32 CFG合成，FlowUniPC依据历史状态做多步预测/校正，更新latent，再覆写条件latent的首cond_t片。下一步必须等待本步scheduler/inpainting完成。参考CFG为同进程顺序两个forward；batched CFG、两rank CFG parallel及其broadcast是另外的互斥源执行合同，不能算两遍。CFG两支真实L、路由及mask可不同。

官方single-GPU脚本默认example_4，其JSON duration=5，fps=24。runner会把JSON duration补入并用utils.num_frames_from_duration计算121帧，因此不能直接沿用CLI默认9帧或pipeline默认81帧。480×832、121帧对应latent [1,16,31,60,104]，patch [1,2,2]后Nv=48360。以上是静态解析推导，尚非运行shape回执。实际joint长度S=Nv+L_cond或Nv+L_uncond，L必须由processor/encoder输出记录。来源：source/scripts/single-gpu/run_moe_ti2v.sh、source/lingbot_video/runner.py:1357起、utils.py:22起、pipeline_lingbot_video.py:280起。

## 3. DiT算子拆分

输入先按(f,h,w)形成patch，特征顺序(pf,ph,pw,c)，64→2048投影；文本为2560维RMSNorm→Linear2560→2048→SiLU→Linear2048→2048。视频与文本拼成joint序列，两类token都经过48层attention与MoE。三轴RoPE维度32/48/48；视频时间索引从该样本真实文本长度+1开始。RoPE表有CPU FP64频率准备、FP32/complex64生成和设备索引边界，不能视为零成本。

一次forward还有FP32 time projection/MLP和token-level六组调制生成；六组shift/scale/gate不是每层再做一次相同time MLP。每层将temb6加到自己的learned scale_shift_table，tanh两组gate；随后：

RMSNorm → scale/shift → BF16 cast → Q/K/V三投影 → Q/K逐head RMSNorm → complex RoPE → 非因果joint attention（QK/mask/softmax/AV）→ O投影及bias → norm_post_attn → gate/cast → 残差 → RMSNorm/scale/shift/cast → routed MoE＋shared → norm_post_ffn → gate/cast → 残差。

DiT是16头、head_dim128的MHA，不是Qwen3的32Q/4KV GQA；不继承KV四份复制、cached decode或跨去噪步KV复用。对packed多个样本必须隔离attention，不能把不同视频任意拼成能互相关注的token序列。Flash/SDPA只在逻辑上拆QK/softmax/AV，不能假设完整score落HB。

48层之后是final time modulation、无learned affine的LayerNorm、scale/shift、输出投影2048→64；源代码先投影全部joint token，再取视频token和unpatchify。不能提前只投影视频而称源工作量未改。来源：source/lingbot_video/transformer_lingbot_video.py:227起（文本）、235起（attention）、940起（block）、1130起（主forward）。

## 4. MoE语义与真实采集边界

FP32 router [S,2048]×[2048,128] → sigmoid → 加correction bias仅用于选择 → 四组各32专家，组内Top2求和 → Top2组 → 屏蔽其他组 → unsorted Top8。加权时从无偏置sigmoid scores gather，归一化乘2.5后转输入dtype；存在语义padding mask时又屏蔽/重新归一化并乘2.5。实际dispatch权重与router原返回权重都要保存，不能重算普通TopK替代实际输出。

pack丢弃零权重slot，按expert稳定排序，保留sorted_positions和sorted_scores。参考backend为grouped_mm，pad为vectorized、reorder为sort、restore为scatter；每expert padded计数为8×ceil(max(m_e,8)/8)，包含m_e=0的最少8槽。有效assignment和dummy GEMM算术分账；若换为for-loop跳过空专家，是backend变体，需另验等价，不静默删掉源成本。

每个专家w1/w3→SiLU乘法→w2，中间维768，三矩阵权重共9MiB。shared专家也是I=768，不是配置中备用dense MLP的6144；独立于Top8，对全部输入hidden执行，最后与routed输出相加。语义padding的routed权重可为0，但shared路径和某些CP dummy仍发生源算术；要保留这些实做量或证明合法消除，不能以“无有效输出”当“从没计算”。

默认restore恢复[token,actual Top8-slot,H]，用FP32乘法与slot轴求和再cast。按rank任意先sum、或先BF16加权，不自动数值等价。目标EP返回必须保留actual slot和原合并合同。源码MoE是本地GroupedExperts，源显式all-to-all在Attention CP内；EP16跨NPU是本交付的候选lowering。

真实trace每条保存run/sample、输入与版本SHA、seed、去噪step/实际timestep、CFG分支、层/module、rank及并行组、batch、joint token种类video/text/semantic-padding/CP-padding、局部与全局索引、视频(t,h,w)或文本位置、actual slot/专家ID、选择分数与实际权重dtype、pack/unpack身份。完整logits/scores设小样本全量核验，主trace可保留紧凑IDs/weights+共享元数据。若按uint16专家ID+BF16权重，纯视频下界40×2×48×48360×8×4=5942476800 B，尚不含文本、身份和压缩开销；每份完整FP32[S,128]数组累计约95.08GB，不能无预算同时全存三份。来源：transformer_lingbot_video.py:354—427、446起、573起、736起、896起。

## 5. 条件编码器与VAE范围

Qwen3-VL的vision是24层、hidden1024、16头、MLP4096；patch Conv3d内核[2,16,16]，含位置插值、视觉RoPE、LayerNorm、多头attention及GELU MLP。视觉5/11/17层输出经过deepstack merger，与最终merger输出一起进入text core；text core36层、H2560、32Q/8KV、head_dim128、dense SwiGLU I9728，前三text层按视觉位置注入三组deepstack特征。输出hidden选择、前缀crop、maskcrop和batch1尾padding移除均保留。它不是MoE子模型。

Wan VAE的weights是FP32，base96、dim_mult[1,2,4,4]、两residual/尺度、三个采样尺度temporal_downsample=[false,true,true]；有causal Conv3d、RMSNorm/SiLU、shortcut、resample、mid attention、quant/post_quant 1×1 Conv、Gaussian采样及latent mean/std变换。attn_scales=[]不意味着完全没有attention，mid block仍有attention。encode/decode的首chunk与后续chunk使用temporal cache，必须保留cache读写完成依赖。

需特别保留源精度边界：TI2V encode_image_latent在CUDA上显式开启BF16 autocast，即便VAE权重FP32；decode默认FP32 VAE不因此自动启用BF16。不能把所有VAE运算一概写成FP32，也不能把它整体套FP16阵列吞吐。此处模块图由固定依赖源码＋本模型config/header绑定，实际融合、cache迭代和tile shape仍待真实forward。

## 6. 目标映射与守恒

规范V3.6为16 NPU、4×4 mesh＋gateway，总HB8GiB/16×512MiB CH，每NPU4MiB SRAM/8 SRAM Bank，64×64阵列的FP16规格2048 MAC/cycle且FP32累加；FP32 vector/reduce各16ops/cycle。Ni与CHi整体25.6GB/s、32B事务；4逻辑投影Bank、16decoded DRAM Bank和8SRAM Bank不同。规范源码不改，原host8GiB不改。来源：[V3.6 YAML](../whisper_operator_inventory/target_architecture_v3_6/target_architecture_v3_6.yaml)。

首个候选为Attention-TP16＋EP16：head h由Nh负责，QKV投影列分片、O投影行分片，partial归约后bias只加一次。unique token origin o(t)=global_joint_token_id mod16；每个origin只路由一次并发出每个有效assignment一次。p_l(e)=e mod16，每rank8专家/层。owner等token与HB/SRAM权重就绪，再计算、返回origin；origin按源slot顺序combine，加自己的shared输出，postnorm/gate/residual后同步下一层hidden。shared权重可逐层在16rank复制，但每个有效token只在其origin执行一次，复制容量与更新成本显式计入。

Attention-DP为独立完整样本的候选，不能把任意视频token当独立request破坏joint attention；CFG两支是否拆replica须另外冻结。源码CP/Ulysses为另一候选：sequence↔head四次all-to-all，degree应整除16 heads，并记录CP padding；不能同时按TP16 collectives又加一整套CP交换。FSDP是GPU加载/参数分片合同，不能当目标expert parallel。

每条通信带sample/step/branch/layer/global-token/actual-slot/expert/owner身份。对所有origin/owner计数n[o,r]，远端dispatch与返回各n×2048×2 B，元数据另算，本地owner bypass不造NoC流量。Ramulator末事务完成、PopNet最终收包、集体通信完整归约及HB安装可见才解锁消费者；host/PCIe/gateway不得离线相加冒充耦合时序。详见TARGET_LAYER_COMPLETION_GRAPH.json和COMMUNICATION_LEDGER.json。

## 7. 容量和数值阻断

本轮只读取safetensors头部：[MODEL_HEADER_AUDIT.json](MODEL_HEADER_AUDIT.json)记录DiT 977张量、30084512320元素、净张量60272785536 B，441张F32/536张BF16；text encoder713张全BF16、净8875631616 B；VAE194张全F32、净507570124 B。三个组件净张量合计69655987276 B，区别于69694390066 B完整交付文件大小。没有从头部求值权重。

原host8GiB＋HB8GiB不可能容纳完整只读后备，不把A3B活跃规模当权重容量。每expert9MiB已超4MiB SRAM，EP16每rank全48层routed共3456MiB，超512MiB CH；即便每次只装一层，激活、双缓冲、router/shared和collective工作区峰值还要单独核。

仅Nv=48360不含文本时，一份BF16 hidden约198MB，FP32 temb6约2.377GB；若错误全物化16头FP32 attention scores约149.676GB，默认restore的BF16 unsorted约1.585GB及FP32 cast约3.169GB。此为源码逻辑数组大小下界，不是实测峰值，也不意味着FlashAttention真写score。目标需要tiled attention、流式slot合并、temb6按token生成/广播等候选；每项都须数值边界与生命周期证明，不能直接删除成本。

建议下一阶段评估“8GiB HB不变＋128GiB host只读后备”显式overlay，但本聊天没有选择或执行该容量配置，不能自动继承mini-SWE批准。若不采用overlay，则必须明确外部存储及实际服务路径，或把任务范围限制为已装载片段，不宣称完整系统。所有BF16/FP32矩阵、sigmoid/tanh/rsqrt/exp、TopK/scatter、FP32 combine和scheduler特殊函数都先做原语合同；FP16吞吐不能移用。详见CAPACITY.json及后续计划。

## 8. 当前结论

任务图和候选映射已具备可复查的源码、形状、dtype与依赖结构。图不是实际执行轨迹；条件模块逐tile、BF16目标能力、host后备、HB/SRAM峰值、真实路由、通信时序与净策略收益仍未验收。结构工作完成不改变此前自然Bank实验NO_PROMOTION，也不预设新视频负载会产生收益。

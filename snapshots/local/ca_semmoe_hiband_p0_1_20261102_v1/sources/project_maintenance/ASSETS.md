# 全项目资产总览

2026-11-02 swe_qwen3[持有权/收尾v8](../swe_qwen3_lifetime_owned_20261102_v8/REPORT.md)：完整两层CPU759投影/56阶段/12严格输出KV、3920分配回收独立通过；真实单活动端点两轮和持有权泄漏拒绝通过，非全层原生。[v7可移植完整基线](../swe_qwen3_continuous_portable_20261101_v7/REPORT.md)仍运行，v8冻结队列仅在其严格最终通过后启动。v5 ISA方法修订停止保留，原BF16/host128-HB8/GPU差异不改，1—7PARTIAL。

2026-11-02 LingBot[完整TP两轮检查](../lingbot_step5_full_tp_20261101_v6/CHECK_20261102.md)：第一轮16rank双CFG98869查询及208590 NoC回放完成，独立core/O/FFN输入零差异；第二轮条件前43136行通过、无条件未开始。控制器及独立审计归档任务存活，无失败文件、未重启；最终两轮回执未生成，步骤5仍PARTIAL。MoE检查点拼接非连续全层时序，原混合BF16-FP32/host128-HB8/目标GPU0及门槛不变。

2026-11-01 LingBot[CPU成本样本](../lingbot_step5_cpu_fda_20261101_v8/REPORT.md)及[真实CPU回调双轮](../lingbot_step5_cpu_service_20261101_v9/REPORT.md)有限通过：Sniper执行单查询K/V及O末片，2304 FP32软件参考与BF16原GPU逐位通过；回调两轮各516时钟/217域记录/41水平PopNet，第二轮反馈全应用、10子进程0，94载荷SHA及补取原始CSV本地重算通过。仅单活动NPU/HB、非完整CPU成本/缓存维护认证。完整TP第一轮条件16头各24704行、50593792 BF16 core元素零差异，仍运行；步骤5 PARTIAL，原混合精度/host128-HB8/目标GPU0不变。

2026-11-01 LingBot[完整MoE两轮验收](../lingbot_step5_full_ep_20261031_v5/COMPLETION_20261101.md)：每轮98869行/607451136边界元素逐位通过，84741主审计/160Bank检查、21536宏DAG节点/96880水平PopNet及全部第二轮反馈通过，66子进程0。原358成员包及补329成员包本地SHA通过，192数值数组4.86GB留113、525项SHA索引；本地重建DAG/Bank通过，非本地重算全量GPU数值。[完整TP attention/O](../lingbot_step5_full_tp_20261101_v6/REPORT.md)已独立后台启动，16线程/nice10/24h上限、独立core首差观察及审计归档；新FFN全量一致才拼接已验收MoE检查点，非连续完整层时序。新K/V目标GEMM、CPU/PCIe/完整算子与SRAM成本及收益仍未认证；原BF16-FP32/host128-HB8/目标GPU0不改，步骤5 PARTIAL。

2026-11-01 swe_qwen3[布局/缓存v4](../swe_qwen3_alias_cache_20261101_v4/REPORT.md)新增有限验收：CPU功能回归布局缺口768→0；原生缓存小探针3目录写回回执及86.2ns模拟等待、CPU后续绝对时间门控/跨集合miss和不维护对照通过。237成员2.11MB本地独立SHA/日志/SQLite通过。旧容器依赖与ABI风险经隔离完整重编译修订，失败保留；新路径完整两层未跑，动态释放/完整时序和1—7仍PARTIAL，原BF16/host128-HB8/GPU差异保持。

2026-11-01 swe_qwen3[完整两层v3](../swe_qwen3_continuous_lowering_20261031_v3/REPORT.md)两轮有限验收完成：每轮759矩阵/32形状、4320 CPU软件调用，1626944原始FP32元素/56阶段/12输出KV严格通过；98079水平PopNet/70子进程通过，613成员安全包本地独立SHA/数值/时钟复核通过。旧v2运行中记录已过时，停止历史保留。[v4布局/缓存修订](../swe_qwen3_alias_cache_20261101_v4/REPORT.md)仅CPU控制回归确认布局缺口768→0，非新原生通过；缓存队列完成门控候选待验，完整时序/动态释放及1—7仍PARTIAL。原BF16、host128-HB8、GPU差异保持，无策略收益。

2026-10-31 LingBot[步骤5连通层两轮](../lingbot_step5_coupled_20261031_v4/REPORT.md)：真实16NPU/16HB，双CFG各64查询全KV上下文，保序O→自由router→owner专家重算→返回/层输出两轮逐位通过；22055数值传输/160Bank检查、每轮5774 DAG节点/1792水平PopNet及全部第二轮反馈通过，66子进程0，739载荷50.16MB本地SHA与194数组对逐位通过。v2竞态和v3主动停止保留，源兼容CPU数学/宏代理非完整opcode时序；[全98869行MoE子图](../lingbot_step5_full_ep_20261031_v5/README.md)已通过门控后台启动，16线程/nice10/12h上限及独立审计归档，仍运行。目标GPU0/混合BF16-FP32/host128-HB8不改；完整TP attention、CPU/PCIe/完整SRAM成本及策略收益未认证，步骤5 PARTIAL。

2026-10-31 swe_qwen3[完整两层CPU/FP32/SRAM续版](../swe_qwen3_continuous_lowering_20261031_v2/REPORT.md)：759矩阵/32形状及CPU软件服务已接回统一入口并运行，未完成目标验收。117载荷冻结/预检/CPU oracle快照本地SHA通过；原61.07GB权重外新增16GiB指数/128KiB SiLU通用兼容数据留113，计host128容量与访存，非新增模型权重。标量v1停止保留；v2受控12小时、独立FP32/NoC/安全归档门控，BF16/host128/HB8/GPU差异不改，1—7PARTIAL。

2026-10-31 LingBot[步骤5固定通信首门](../lingbot_step5_ep16_20261031_v1/REPORT.md)：双CFG790952次真实分配EP16序列化/槽位恢复及202483712个FFN BF16元素通过，1940条预定子集真实字节PopNet、12242独立检查及36载荷SHA通过。O分片FP32求和130/106差异保留，同输入逐rank FDA累加器传递零差异；尚未完整TP16或payload耦合NoC/DAG，容量仅静态，步骤5 PARTIAL。原精度/host128-HB8/目标GPU0，无策略收益。

2026-10-31 LingBot[步骤4有限功能收尾](../lingbot_step4_native_repair_20261031_v6/COMPLETION_REPORT.md)：双CFG98869行单层CPU逐位一致及30944项独立审计通过；新5路split-K/FMA原生router行128 FP32与GPU/独立Windows标量逐位一致，75445检查/10283事件/33312事务及8载荷SHA通过。导入失败和计数失败保留；累计原生尝试3（新失败1/成功1），物理0/本轮GPU0。原BF16-FP32/host128-HB8不改；仅CPU单层功能及原生单行事件门，完整层目标lowering/时序、48层40步/VLM/VAE/TI2V及策略收益未认证。

2026-10-31 swe_qwen3[CPU/FP32 lowering/SRAM Bank新增实跑](../swe_qwen3_codec_fp32_sram_20261031_v1/REPORT.md)：完整16节点两轮反馈及419载荷本地验收通过；新增M1与真实M6专家gate的CPU转换/原FP32归约/真实4MiB SRAM服务两轮通过，145/142载荷SHA及本地独立数值复算通过。Bank端口/映射为显式研究点，CPU缓存维护成本未认证；新路径尚未接回完整层，1—7PARTIAL，原BF16/host128/HB8、GPU差异保留。

2026-10-30 22:54 swe_qwen3[完整16节点phase1](../swe_qwen3_legosim_16_layers_20261030_v3/README.md)：修正CPU/DRAM单位后，prefill/decode连续两层56阶段、12输出KV、CPU双回传及759矩阵（450远端）/61fetch通过，160载荷本地SHA、433510时钟观测通过；原包冻结索引单独补取。完整PopNet28316条仍在回放，第二轮和全目标成本未验收，原BF16/host128/HB8与GPU差异不变，1—7PARTIAL。

2026-10-30 swe_qwen3[16节点时钟修订](../swe_qwen3_legosim_clock_fix_20261030_v1/REPORT.md)：原完整PopNet已通过归档；旧CPU/DRAM单位错误的时序不晋级，数值证据保留。CPU2.5/DRAM1.25与向上取整修订，16节点两轮BF16投影、每轮11296时钟观测及816反馈通过，381载荷本地SHA通过。完整两层16节点v3实跑中，prefill L0的14阶段通过，后续须查独立COMPLETE_DELIVERY；原BF16/host128/HB8及GPU差异不变，1—7仍PARTIAL。

2026-10-30 LingBot[稀疏专家split-K恢复](../lingbot_step4_stagewise_20261030_v5/REPORT.md)：旧4差异定位为M148专家gate/up的并行6分区，完整227328元素及原失败131072元素FFN修复通过，仍为隔离合同。新两阶段全98869查询后台验收：A生成完整FFN输入，B自主全路由批量；11776行A资产复用经1660检查，旧B不复用；全层仍PARTIAL，原精度/host128-HB8/目标GPU0保持。41载荷8396965B/归档3931657B本地SHA通过，大载荷留113；未新增目标原生或收益。

2026-10-30 16:37 swe_qwen3[统一两层修复版phase1](../swe_qwen3_legosim_integration_20261030_v1/CONTINUOUS_LAYERS_20261030.md)：CPU双结果回执/56阶段/12输出KV、759权重版本、2998节点及7负对照通过，98修复版载荷本地SHA通过；原EOF失败不覆盖。完整156105条PopNet回放在途，非完整时序或全16目标认证，1—7仍PARTIAL。

2026-10-30 swe_qwen3[完整两层统一入口续作](../swe_qwen3_legosim_integration_20261030_v1/CONTINUOUS_LAYERS_20261030.md)：首轮真实完整两层56阶段/12严格输出KV及759次权重流通过，156105条NoC回放结束；CPU decode FIFO EOF导致端到端未过。持久写端修复版实际重跑中，最终需检查独立回执。114审查载荷本地SHA、7负对照通过；原BF16/host128/HB8与GPU差异保持，诊断拓扑不认证全16或完整时序。

2026-10-30 swe_qwen3[统一入口真实运行](../swe_qwen3_legosim_integration_20261030_v1/PROGRESS_20261030.md)：InterChiplet/PopNet隔离构建、BF16 FIFO/外部HB往返及真实Sniper-NPUSim-Ramulator-PopNet残差norm通过；两轮315 delay反馈，5 CPU ROI/5 NPU进程及7验收负对照；1191载荷SHA通过。单活动HB512MiB，未完整层/KV/全16NPU或完整时序，第1—7步PARTIAL。源码上传授权已实施，旧拒绝是历史。

2026-10-30 LingBot[原精度CPU数值适配v4](../lingbot_step4_bitexact_20261029_v4/REPORT.md)：rsqrt/exp、自主router全序列、完整K/V及双CFG各64查询的完整上下文串联层输出逐位通过；67独立检查/12负对照，compact review192载荷33678282B/外包16577082B本地SHA通过，大型数学域表/全KV留113。全98869查询单层验收后台进行，尚未完成，整体PARTIAL；旧失败保留，原BF16/FP32、host128/HB8、目标GPU0，新原生0/物理0。数学表host开销另计，非目标时序或HiBand/Sem-MoE收益认证。

2026-10-30 swe_qwen3[统一Legosim接入准备](../swe_qwen3_legosim_integration_20261030_v1/REPORT.md)：904交付源码SHA、InterChiplet隔离构建配置、launcher及REPLAN已备；旧113入口缺Boost1.65且树内无NPUSim。源码构建包1911127 B未上传，自动审批阻断需具体源码上传授权；统一运行0，未声称已接入或BF16时序通过。

swe_qwen3跨日[softmax连续接入](../swe_qwen3_softmax_primitive_20261029_v1/REPORT.md)：显式SLEEF16依赖FP32软件原语实际运行两层prefill/decode；8调用40阶段、72控制712088元素、56阶段/12输出KV及门控审计通过，127载荷SHA通过。共享SLEEF不是独立exp认证；失败保留，host回退350→342，GPU GEMM/softmax差异不变，步骤3PARTIAL。累计原生19/Sniper3/物理0，本轮GPU0，原BF16/host128/HB8。

2026-10-29 swe_qwen3[独立norm连续两层](../swe_qwen3_norm_20261029_v1/REPORT.md)：FP32 cascade8/rsqrt软件原语实际接回；16调用64阶段、72控制3489018元素及56阶段/12输出KV精确，last-reader/交接审计、106载荷SHA通过。host回退398→350，GPU GEMM/softmax差异及完整时序缺项保留；原BF16/host128/HB8，步骤3PARTIAL，累计原生17/Sniper3/物理0。

2026-10-29 swe_qwen3[连续BF16向量原语](../swe_qwen3_continuous_vector_20261029_v1/REPORT.md)：实际新增两层prefill/decode原生事件运行；12输出/KV、56阶段、374向量节点精确，131072元素C挑战及last-reader/2交接/4KV审计通过；92载荷本地SHA通过。host回退772→398，不代表收益；原BF16/host128/HB8、GPU GEMM/softmax差异保留，步骤3PARTIAL。累计原生16/Sniper3/物理0，本轮GPU0。

LingBot步骤4续作（2026-10-29）：[报告](../lingbot_step4_completion_20261028_v3/REPORT.md)仍PARTIAL、未完成。独立C BF16专家软件核935阶段/5898240元素及两CFG记录路由MoE对单线程CPU源逐位一致，4线程295失败保留；适配器未知几何/bias/特殊函数显式拒绝。197738行H2048 mean(square)对原GPU FP32逐位一致，但正确RNE rsqrt因子41631不同、postnorm仍1314 BF16差异；给定GPU exp的12655232个score加除及后处理通过，不是自主sigmoid。exp2替代候选7权重差异保留；旧GEMM/attention/全层未过。532项独立审计/12负对照及281载荷本地SHA通过；新增1次外部数学参考约1.64GB峰值、完整模型调用0，目标GPU0/新原生0/物理0，LingBot原生累计1，host128/HB8与原混合精度不变。

## 10月28日维护事实基线（取代此前当前状态，历史范围保留）

维护日期：2026-10-28。原BF16/混合BF16-FP32、host128 GiB/HB8 GiB为显式研究配置，原host8规范未改；目标GPU为0，外部GPU参考与模拟器运行分别计数。以下不构成完整系统时序或HiBand/Sem-MoE/BDPL策略收益通过。

| 主线 | 当前完成范围 | 未通过与适用边界 |
|---|---|---|
| LingBot真实采集 | [步骤3报告](../lingbot_step3_capture_20261028_v1/REPORT.md)：3936路由及共享调用，完整40步3840条、28完整fixture；31568项审计及6负对照通过，单步开关及此前40步latent逐位一致 | 已见example_4，非独立留出；采集完成不是目标全层功能通过。约9.68GB采集载荷留113，本地仅compact review，72载荷，不是全量回传 |
| LingBot router修复 | [步骤4 v2](../lingbot_step4_router_repair_20261028_v2/REPORT.md)：同GPU scores的98869行Top8槽位及790952个BF16权重逐位一致；309项独立审计通过 | 同logits后CPU sigmoid仍6权重差异，自由GEMM/sigmoid仍93；完整上下文64查询/串联block仍有差异。两版各43比较13一致/30差异，不能宣称完整层PASS；1次原生FP32行对顺序参考一致、对GPU121/128不同。总体PARTIAL |
| swe_qwen3连续两层 | [四项门槛](../swe_qwen3_step3_four_gates_20261028_v1/REPORT.md)：68项前半层检查，258组645120元素batch核对，两层19-token prefill/1-token decode的4输出及8 KV严格项通过；2次连续HB交接、4次KV追加 | N0串行矩阵/存储与772次显式host回退；host成本null，非纯NPU、TP16/EP16或完整时序。139420事件/107915094事务、SRAM703744 B/HB范围102833632 B为本合同。累计原生14、Sniper3、物理NPU0；不把历史各片段重复求和 |
| swe_qwen3 prefill定位 | [首差异报告](../swe_qwen3_prefill_first_difference_20261028_v1/REPORT.md)：内部首差为input RMSNorm FP32 mean(square)9行，但回BF16消失；首次持续BF16差为同输入Q/K/V GEMM74/5/3元素。50阶段/100二进制绑定旧路径 | 定位非修复。原4249输出、10路由slot及softmax FP32差异保留；10 slot含9同集合换序与1边界平局换专家，不能全部归因QKV。仅1次有界外部GPU前半层诊断，未重跑完整层、无新增目标原生 |
| agent验收 | [冻结留出](../swe_qwen3_step3_holdout_20261026_v1/REPORT.md)：两开发及两Astropy留出均未修复，留出0/2、空补丁；采集/证据工作完成 | 不是总体成功率，也不是agent就绪。已用留出不得重称未见；[v2/v3复核](../swe_qwen3_step3_progress_20261027_v3/REVIEW_20261027.md)仍官方未过，重复同两开发非独立样本。v4 README/启动记录不能替代最终官方评分；本轮未确认其功能准入 |

归档与授权：LingBot采集完整数据、router两版约3.13GB输出留113，本地分别为72载荷/297成员review子集，原任务回执核SHA不等于本维护重验全量。swe留出约1.56GB包307载荷、连续两层260载荷及首差异本地审计按对应报告范围保留。首差异报告已记录用户批准后旧报告上传113并核SHA；此前上传拒绝、留出正文拒绝均为历史，不再写成当前同一操作阻断。旧第二阶段7.45GB/Q1—Q3本地20文件交付沿用原回执，无新增网盘上传证据。

四负载继续为非MoE辅助验证资产，旧有限功能/原生事件结果不撤销，不进入MoE核心机制收益证明。新两MoE路线已经超出26日“未下载、未采集、原生0”阶段，但完整目标时序与实际策略净收益仍未建立。采集、CPU一致、GPU一致、原生事件因果与净收益分别验收。

本轮仅核对本地上述原报告及两专责聊天最近3轮；非全分页重读，不更新其余聊天读取日期，不连接113、不运行实验、不重验大型载荷。源目录早期REPORT/NPU0/下载中快照限原日期；本指南归并后以本节和具体后续报告解释。历史逐条补记原字节见project_maintenance/history/before_20261028_update/。

以下为26日及更早历史合同与资产导航；与前文冲突的状态按日期理解，不作为28日当前结论。

## 当前最短入口

### 10月26日真实MoE benchmark选择与准入状态

选择已明确，执行验收尚未完成：“推荐HiBand与Sem-MoE负载模型”对话最终选择LingBot-Video-MoE-30B-A3B的基础TI2V视频负载，以及mini-SWE-agent＋SWE-bench Lite、现有Qwen3-30B-A3B MoE后端。两条专责聊天已建立。本维护只读取历史，不创建新聊天、不接管后台资产任务；“选为benchmark”只表示进入验证，不是可运行认证或HiBand/Sem-MoE/BDPL收益通过。

| 候选/路线 | 当前证据与定位 | 阻断、历史修订及收益边界 |
|---|---|---|
| LingBot基础TI2V | [盘点](../lingbot_ti2v_feasibility_20261026_v1/REPORT.md)、[最小协议](../lingbot_ti2v_feasibility_20261026_v1/MINIMAL_PROTOCOL.md)：固定源码dd5c231e、权重修订f2e538f6，48层/128 routed experts/Top8＋1共享专家；公开视频推理入口及真实router可追溯。基础模型/文本编码器/VAE/源码清单约69.69GB，不含refiner | [后续下载观察](../lingbot_ti2v_feasibility_20261026_v1/DOWNLOAD_PROGRESS.json)已是DOWNLOADING_CONFIRMED_NOT_COMPLETE，早期REPORT/STATUS的“未下载/SSH别名失败”是前一阶段快照。只记录最后可读观察，不认定进程此刻仍存活或下载完成；本地未取得最终验收回执。依赖、单/双卡内存拓扑与推理仍未验收。是视频生成基座，非机器人动作闭环；无真实路由采集/模拟器/策略收益结果 |
| mini-SWE-agent＋Qwen3 MoE | [预检与草案](../mini_swe_qwen3_preflight_20261026_v1/README.md)、[后续只读资源报告](../mini_swe_qwen3_preflight_20261026_v1/REMOTE_RESOURCE_REPORT.md)：SSH已恢复；现有16权重分片约61.07GB，config/index哈希与历史一致。后续专责聊天记录源码已校验，正在逐分片核验/独立复制至`/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1` | 只读报告未重算61GB全分片SHA；后续复制完成需该远端目录STATUS.state=COMPLETE_VERIFIED及成员/权限清单，当前本地无此最终回执，不能写已验收。该复制任务仅源码/模型，不含SWE任务数据、镜像和推理依赖。模型兼容性/命令闭环、任务修复、真实prefill/decode路由采集和目标平台执行均未通过，任务/推理/仿真仍为0 |
| ScaleZero | [固定提交公开交付核查](../scalezero_public_audit_20261025_v1/REPORT.txt)：MoE实现和训练配置存在 | 在所查公开渠道未找到匹配的训练后checkpoint；不是全网不存在证明。Atari eval示例默认未启用相应MoE、权重占位且含训练更新，不是免训练即用负载。此前“结构候选”推荐收紧为暂缓近期正式准入，无训练/推理或收益 |
| BEVFusion | [固定提交静态审计](../bevfusion_model_audit_20261025_v1/REPORT.md)覆盖15份非build源码/头文件和全部3个ONNX/ORT模型，关闭检测头结构未知项 | TopK选200个检测候选，Softmax为注意力，非专家路由。排除MoE核心benchmark，仅可保留通用算子/NoC/布局扩展候选；静态结构检查不是数值或执行认证，不覆盖旧build二进制。BDPL当前MoE/tile合同和拟合参数不能原样搬用 |
| UnifoLM-WMA-0与其他备选 | 本轮读取“评估 UnifoLM-WMA-0 作为基准”的配置/源码分析对话：所查官方主干无稀疏专家路由，属于非MoE备选；精确适用版本与原来源保留在对话记录 | 本维护未重新下载或审计其外部源码，不将历史回答当新增独立验证。TD-MPC2、KernelAgent＋KernelBench等保留推荐讨论，未替代最终两条验证线，也未获得本项目性能认证 |

LingBot的下载清单为141文件/69694390066 B，refiner排除；这是下载计划总量，不是已完成字节。最后观察时间见DOWNLOAD_PROGRESS.json（UTC），其中10—14小时估计只属于启动时观察，不作为现在的剩余时间。mini-SWE的20—30分钟同为历史估计，不是完成证据。两边新建目录/文件的其他本机用户可读要求有协议与脚本，最终完整性/权限验收未在本维护可读回执中确认；父目录可遍历或部分文件755/644不等于全部文件/跨账号访问已验收。

采集与计时合同：LingBot记录实际router返回值，并区分padding后的有效dispatch权重、共享专家、去噪步/CFG/rank/视觉token位置；不重算普通Top-k代替真实选择。mini-SWE记录自主生成的prefill/每次decode、真实工具到达依赖；旧teacher-forced cached decode不能替代自主修复会话。CPU测试/容器等待不计作NPU计算，GPU时长不当目标NPU周期；少量开发样例不能声称总体成功率。真实路由存在也不自动证明Bank/NoC/热处于关键路径。

### 功能、时序与策略收益分别验收

| 证据级别 | 截至本轮维护时点的结论 |
|---|---|
| 选择/静态资产与下载 | 两条真实MoE路线进入验证，下载/复制有后续观察，最终交付未在本地确认；不把预检完成写成benchmark就绪 |
| 功能验证 | 四负载的FC1、开发Block0、辐射混合链、几何子合同已有有限结果；两条新MoE路线尚无推理/任务/路由运行验收 |
| 原生时序/因果验收 | 既有四负载部分子合同有NPUSim/Ramulator/PopNet完成门控、容量与依赖审计；CPU功能求值与设备事件代理分清，目标CPU/hostlink、逐Bank仲裁/物理校准等边界仍在。新MoE线尚无对应目标平台执行 |
| 实际策略收益 | 没有新增HiBand/Sem-MoE/BDPL净收益证据；第一/第二阶段自然开发与V4仍按原合同NO_PROMOTION，热压力与完整归档不改判收益 |

### 归档交付：已完成旧证据包与在途新模型分开

[第二阶段本地回执](../page_management_stage2_natural_v2/DELIVERY_COMPLETE.json)继续记录约7.45GB、1962载荷文件/98运行绑定已验收；[Q1—Q3本地归档](../outputs/qwen_q1_q3_full_archive_20261024_v1/LOCAL_SAVE_REPORT_20261025.md)为20文件5351897685 B，含对应镜像/依赖，未取得百度网盘上传的新回执；[四负载图谱](../four_workloads_operator_graph_v3_6_20261025_v1/DELIVERY_COMPLETE.md)此前后续明确授权交付113成功，包内上传拒绝是历史。它们均不证明新LingBot/mini-SWE模型资产已完成交付。44.17MB代码ZIP传113也不是模型运行或性能认证。

本轮只核对本地报告、机器清单及分页对话，不连接113或重读数GB载荷；旧验包数量归于原任务回执，下载当前存活/完成状态暂不能独立验证。保留源报告的早期快照与失败，不改其受保护内容；本维护的新索引负责给出分阶段解释。

2026-10-25新增[ScaleZero公开交付核查](../scalezero_public_audit_20261025_v1/REPORT.txt)：固定main提交3be29ae1，本地静态核查源码、Releases、PR与HF索引，未找到匹配的公开训练后checkpoint。MoE训练配置存在，但Atari eval示例默认关闭MoE、权重路径占位且入口含训练更新；不属于免训练即用bmk。作者本地预训练路径不等于公开下载。无113、训练或推理；拿到匹配权重与配置后可另建纯推理采集合同。

2026-10-25新增[BEVFusion源码与模型静态审计](../bevfusion_model_audit_20261025_v1/REPORT.md)：固定公开提交77533e5f，全部15个非build C++源码/头文件及3个ONNX/ORT按Git blob核验；151/246/246节点展开，优化ONNX与ORT节点/属性/权重内容一致。TopK为热图200候选选取、Softmax为注意力，未含MoE；Sem-MoE核心benchmark排除，HiBand与通用页布局仅辅助候选。现行BDPL绑定MoE/tile合同，不能直接移植拟合系数。无模型推理、113或新仿真，预编译二进制同一性未认证。

### 四负载：辅助验证资产，完整系统仍未认证

最新“分析新负载算子切分”对话已明确：四负载退出MoE机制收益的核心benchmark，保留为算子、访存、NoC与映射工具链的辅助验证资产。DINOv3和已核对OLMoEarth Block0是稠密Transformer；遥感辐射/几何是传统数值流水线，不能笼统称四个稠密神经网络。四者没有可用的MoE专家路由，Sem-MoE记N/A；不新增合成专家冒充真实MoE。此为研究定位调整，不撤销已有有限验收，也不授权本维护继续实验。

| 负载/合同 | 已确认的最新范围 | 仍未认证或阻断 |
|---|---|---|
| DINOv3 | [真实FC1](../dino_fc1_v3_6_step3_20261025_v1/REPORT.md)原FP16 fixture在N0/CH0完成分块功能、32 B事务、容量/依赖验收；843055104 MAC为单倍。两参考在0.01+0.01×绝对参考值容差内，最大绝对误差1.0/1.4173583984375，非逐位一致。[合同复核](../dino_contract_audit_20261025_v1/REPORT.md)另核原ZIP16分片SHA | 完整Block0同源20项输入/参数和19阶段Golden仍缺；完整维度校验源码已存在，不能再称全块源码不存在。TP16仅静态列切分，未运行DINO多NPU/NoC；FC1外部输入不能由shape相同推定为完整LN2输出 |
| OLMoEarth | [单cluster](../olmoearth_v3_6_integration_20261025_v1/REPORT.md)与[TP16](../olmoearth_v3_6_multi_npu_20261025_v1/REPORT.md)为同一开发Block0；TP16完成33项数值检查和活动16-router子mesh的2880消息、180 MiB原生通信门控；补偿实际32614907904 MAC为逻辑3倍。新增[区间因果审查](../olmoearth_collective_causality_20261025_v1/REPORT.md)只读，无新原生运行 | 不含CPU gateway、逐SRAM Bank仲裁、校准特殊函数/物理性能或动态HiBand；中间FP32归约数组未保存，不宣称逐项重验部分和。54,412,064 TP16代理周期与单cluster523,345,780周期不构成完整系统加速认证 |
| 辐射校正 | [R1—R5](../radiometric_r1_r5_v3_6_20261025_v1/REPORT.md)后又完成[新R1—R7混合闭链](../radiometric_r1_r7_chain_20261025_v1/REPORT.md)：原DN重算R5→原R6 CPU→新统计发布→R7原生适配，22项配对逐位一致、17583事件/31205依赖；不是复用旧R6输出。原[R7 CUDA](../four_workloads_step3_cuda_20261025_v1/REPORT.md)功能证据保留 | R4为显式计费FP32比较/归约软件直方图，非原生U32原子；R6发布为CPU语义翻译，非原InterChiplet通信。设备8046542周期不含目标CPU/PCIe/gateway；R8—R10各自原fixture仍缺，完整应用PARTIAL |
| 几何校正 | [G3双FP32软件适配](../r7_g3_v3_6_integration_20261025_v1/REPORT.md)通过原严格容差，普通FP32的77823/81920超限失败保留；29 FP32原语/逻辑乘法及CPUcodec成本单列。[新G7再入口](../geometric_g7_v3_6_20261025_v1/REPORT.md)以保存G6为输入，五项检查、390原生事件有限通过 | 不是原生FP64；未连接G3→缺参G4→G6，也未在新G7轮执行G8。原4096像元全有效，无效分支无原样例覆盖。RPC/DEM/query/FP64 NoData/源影像/G2原代码配置/可靠CRS仍缺，完整几何链阻断 |

这些原生适配的数值函数实际在服务器CPU求值，由NPUSim/Ramulator完成事件、SRAM生命周期或PopNet回调门控；“原生”指模拟器事件/库，不是物理NPU执行或原未改耦合二进制认证。局部32 B桥通过不修复旧256 B ABI路径。聚合SRAM容量通过不等于8个SRAM Bank仲裁通过。四负载完整第3步仍PARTIAL，尚无完整系统性能或净策略收益认证。

### 缺失资产、恢复与交付

- [有界搜索](../missing_workload_assets_113_20261025_v1/REPORT.md)未找到新的匹配缺项，不能推出整台服务器不存在；其CPU R1—R7功能闭链11项是历史阶段，后续混合闭链22项另有新报告，不混计为独立样本。
- [元数据恢复](../asset_completion_20261025_v1/REPORT.md)从原记录重建affine/window/U16 NoData三个文件共74 B，并有G7/G8导出检查；这是语义重建，不是找回原文件SHA。完整DINO源码存在不代表权重/输入身份恢复；官方同结构源码也不能证明同checkpoint。
- [四负载图谱交付](../four_workloads_operator_graph_v3_6_20261025_v1/DELIVERY_COMPLETE.md)已获后续明确授权，113新目录50成员、49份产物哈希通过。包内REPORT的“上传拒绝/未上传”保留为批准前快照，当前以REMOTE_DELIVERY回执为准；结构交付不新增负载运行。
- [第二阶段交付](../page_management_stage2_natural_v2/DELIVERY_COMPLETE.json)与[本地验包](../page_management_stage2_natural_v2/LOCAL_ARCHIVE_VERIFICATION.json)记录7449703197 B、1963成员（1962载荷文件）、98运行及142输入集绑定通过；“回传中”已是旧状态。归档完整不改变NO_PROMOTION/NET_UNVERIFIED。
- [Q1—Q3完整本地归档](../outputs/qwen_q1_q3_full_archive_20261024_v1/LOCAL_SAVE_REPORT_20261025.md)完成于25日：主包15735成员、P1依赖1470、本地补充198项；UPLOAD_TO_BAIDU共20文件5351897685 B，已验包，未上传百度网盘。旧4.27GB包仍只覆盖I8/P1/P2/P3；新包无Q4，不新增热策略结果。

上述载荷验包数量取自对应任务的本地报告/机器回执。本维护仅核对报告与小型证据清单，不重新遍历数GB归档内容，也未连接113、启动/终止实验或上传。

## 1. 研究资产地图（既有研究树）

| 目录/文件 | 资产内容与入口 | 如何使用 |
|---|---|---|
| `whisper_operator_inventory/` | 原始hook算子盘点、CPU/GPU补全、独立pipeline、架构v1到v3.6、映射、耦合与热/PDN实验 | 先读根README和目标版本README；是历史最密集的研究树 |
| `whisper_coaccess_v1/` | WHISPER权重映射、筛查、正式矩阵、随机对照、容量与前缀敏感性、最终报告 | 以FINAL_REPORT和performance.csv为结果入口；历史负结果仍有效 |
| `unified_page_coaccess_v1/` | 统一页级口径、Qwen3算法失败诊断、Qwen1.5真实页采集通路及独立审计 | README、STEP3_REPORT、DIAGNOSIS_CAPTURE_REPORT、step4_fixed_trace_v1/REPORT；不是当前冻结策略入口 |
| `unified_page_coaccess_round12_v1/` | 新请求冷页策略验证、两位置完整页采集、冻结协议、独立验证和证据归档 | REPORT、FINAL_STATUS、protocol.json；旧CURRENT_STATUS可能滞后 |
| `coaccess_transfer_analysis_v1/` | 汇总期间其他活跃聊天新建的迁移诊断资产 | 历史覆盖诊断；后续验证已推进至冻结选择器，详见下表；不要覆盖 |
| `coaccess_transfer_validation_v1/` | 2026-10-18在113执行的共享结构时间核、专家共现按组留一离线验证；冻结协议、修订、结果与证据包 | 两模型当前共现增量门槛均未通过；通用结构模板有开发集代理收益，未补采集或完整仿真。最终报告和独立验收见证据包 |
| `coaccess_definition_audit_v1/` | 统一定义步骤0—2：计数审计、真实图可优化空间、路由/时间诊断矩阵、纯逻辑与历史强对照、有限换页和保存布局 | 两模型有继续步骤3离线研究的诊断空间；T方法含留出信息，不可部署。F_diag限定审计不等于F_full物理容量/地址认证；未补采集或仿真 |
| `coaccess_step3_static_v1/` | 固定静态映射的双组泛化、三折留一、冷专家强度先验、Qwen1.5页/阶段消融、历史同预算对照 | 两模型所有冻结候选均无稳定增量；冷强度总量接近不能替代页对预测。未补采集或仿真，限定抽象约束，验收脚本修复有独立记录 |
| `coaccess_common_static_v1/` | 三组共同静态平均/最差目标、Qwen1.5逐专家逐张量22页均衡、旧共同可行布局复核与强起点补充诊断 | 两模型有共同代理目标空间，但不可部署；严格均衡未胜强共同对照。RESULTS澄清包络门槛、有限搜索与max聚合，V2证据100布局/60直接评分/137文件；不扩大完整仿真 |
| `coaccess_mechanism_audit_v1/` | 第1步信息归因：互斥边分解、保热度页置换、专家/owner关联探针、均衡投影与同起点双分支、Qwen3完整日志检查 | 页位置有热度外信息但迁移未知；新严格最差解1583636胜旧共同参考，修正“严格空间无好解”的推断。Qwen3三组576页覆盖齐全但尚未拟合完整页图；70布局/42直接评分/52文件，未采集或仿真 |
| `coaccess_step2_transfer_v1/` | 第2步精确页相对时间/起点因子化迁移，随机与固定结构起点、严格均衡、历史强参考；Qwen3完整页窗口表示 | 三候选/两起点均无稳定增量，不扩大。Qwen3完整同专家边质量0，只有逻辑结构控制，驻留/全页迁移未认证。V2报告及RESULTS，630布局/75直接评分/9完整页评分/688文件 |
| `coaccess_failure_diagnosis_v1/` | 目标一致性、训练/评价迁移、48个16页精确子问题与Qwen3基线paging/地址审计 | 目标偏差与迁移失败均确认，11局部精确差距不是全局证明；Qwen3基线驻留限定通过、新Bank物化未认证。REPORT、协议、范围验收、56文件证据包；只支持受限Qwen1.5联合统计诊断，不采集不仿真 |
| `coaccess_joint_contract_v1/` | Qwen1.5直接联合窗口矩训练一致性、两强起点、Qwen3离线native及均衡逻辑页物化契约 | 训练门槛失败，未跨组评分；不是跨组检验负结果。Qwen3每专家36页/Bank子空间离线可行、运行时未接入。60布局/18窗口评分/110证据文件，未采集或仿真 |
| `coaccess_granularity_scan_v1/` | 两模型六粒度×四简单策略，粗描述符固定条带对照、实际Bank驻留/容量与成本模型、评分口径补充诊断 | Qwen3较细条带有条件代理收益，不证明逐页状态必要；Qwen1.5跨请求/同请求压力方向可能相反。144布局/432评分，V1保留、V2共181文件；无性能或仿真结论 |
| `coaccess_mechanism_perf_v1/` | 隔离native物化器、两模型既有图切片实际Ramulator/PopNet运行、MLP/单请求反例、floor反事实与查询/迁移成本 | 24运行+3合成回归，MLP1条件收益6.721%—10.593%，MLP16全平；非完整推理，1ns发射间隔不是硬件查表延迟。354文件证据，原始事务留113，无新请求采集/完整矩阵 |
| `qwen_hiband_scope_fix/` | Qwen1.5/HiBand范围修正、bank stress、strict barriers、memory-bank补全、coaccess布局与热点图 | 本目录历史布局阶段见memory_bank_completion_v1/coaccess_qwen15_v1；非当前真实块选择器入口，历史目录不可混并 |
| `qwen3_30b_a3b_v3_6_experiment/` | Qwen3路由、执行图、soft70受控压力、paging、Bank对照、图表和归因 | bank_conflict_v2/STEP4_6_STATUS、STEP7_STATUS；results内按实验manifest定位 |
| `qwen1_5_moe_a2_7b_v3_6/` | PP4×TP4/EP4映射、Sem-MoE路由合同、lowering、synthetic smoke、execution overlay与模型缓存 | README明确合成与真实路由区别；缓存不是普通可删除中间件 |
| `qwen3_8b_v3_5_mapping/` | Qwen3-8B算子图、容量/并行映射 | 解析映射入口README，不代表执行完成 |
| `qwen3_30b_a3b_v3_5_mapping/` | Qwen3-30B三阶段解析DAG、NPU-SIM输入、逻辑通信和容量 | 同上 |
| `qwen1_5_moe_a2_7b_v3_5_mapping/` | Qwen1.5旧架构映射、构建/校验/渲染脚本 | 保留与v3.6的版本边界 |
| `qwen1_5_moe_a2_7b_v3_6_mapping/` | Qwen1.5容量分叉映射 | 先读本目录README，不从相似目录名推断等价 |
| `v3_6_missing/` | 按名称归入V3.6缺项补充资产 | 本轮未对内部逐项验收；不作已补齐证明 |
| `hiband_reproduction/` | 论文身份/来源/假设账本、独立GTP/HIC/SOR/NoC参考模型、113证据、报告和渲染QA | STATUS、README、STEPS_4_6_REPORT；官方数值复现仍受阻 |
| `DeepStack_official_ae/` | DeepStack/TileSight源码、Bank Oracle、预生成图、CPU解析复现工作流 | 独立Linux/Conda项目；预生成图不代替重新验证 |
| `PIMoE_reproduction/` | 算法复现、路由提取、PIMSimulator第三方源码、直接测量/仿真、汇报 | 中文全过程说明与algorithm/README；注意论文伪代码修正的解释性质 |
| `RobotAPP_upload/` | SLAM代表应用、架构和集群精简结果，WhisperApp应用/测试/Trace | README、readme_SLAM、WhisperApp/WHISPER_README；不含全部上游工具本体 |
| `noc_motivation_20260916/` | NoC动机图的数据、图和redraw_noc_motivation.py | 图与原始聚合数据配套保留 |
| `_popnet_microarch_src/`、`_popnet_timing_src/`、`_popnet_v3_3_c2_patch/` | PopNet源码工作副本和补丁 | 下划线目录不等于临时垃圾；先查目标实验来源 |

## 2. 论文、文献与汇报资产



- `paper_261010_stage/`：本地论文阶段副本，含`main_draft1010.tex`、`references.bib`、ACM样式、图、PDF和编译副产物；`original_backup/`保留原版本。历史聊天还操作过D盘`system_chip/260930`和`261010`等目录；本地stage并非已确认唯一主稿。

- `DAC_2026_Draft_Proceedings/`：DAC文献资料目录；本轮只作资产归类，不核验每篇论文身份。

- 根目录汇报：Chipletizer 2.0、CLAP、DFBM、ECPrefix、Flumen、IGNITE、LAD-3D、SpArC、Wang 2026 3D eFlash等PPTX；部分附逐字稿DOCX及`.pptx.inspect.ndjson`。旧版、听懂版、问题强化版均保留，文件名不能作为最终选择的唯一依据。

- 根目录论文PDF：DFBM相关Chen等2026文献及Flumen相关Shiflett等2023文献；本轮不重新提取全文。

- `Opportunity_汇报_三方案与跨用户专家页布局.docx`、`build_opportunity_report.py`：机会点报告及生成脚本。

- `outputs/expert_*`与`artifact_work/`：专家相关研究整理、文档更新脚本及截图；引用研究事实前回到其来源记录。

- `output/`和`outputs/`是两个不同目录；前者含图像、论文架构图、PDF/PPT等输出，后者含专家整理与figures。不要通过重命名合并两者。

- `qwen3_doc_review/`、`qwen_hiband_scope_fix/`相关报告、根`COACCESS_BANK_LAYOUT_QWEN3_QWEN15_REPORT.md`共同构成论文修改证据链；汇报文字不能反过来替代运行数据。



## 3. 传输包、脚本与旁路证据



| 资产 | 内容/风险边界 |

|---|---|

| `deepstack_ae_d8ffb49_source.tar.gz` | DeepStack源代码归档；本轮未解包或比对目录树 |

| `RobotAPP_whisper_bd1b84f.bundle` | Git bundle传输资产；文件名里的提交需实际验证 |

| `target_architecture_v3_4_h2llm*.tar.gz` | V3.4/H2-LLM历史交付包，不改名为新架构结果 |

| `whisper_v3_3_c3_iter2_inputs_20260831.tar.gz` | V3.3历史输入归档 |

| `github_fork_robotapp.ps1`、`github_create_robotapp_pr.ps1` | GitHub外部写入脚本；盘点时不执行 |

| `migrate_target_architecture_v3_3.ps1` | 历史架构迁移脚本；可能改写生成内容，先读脚本 |

| `run_noc_flit_sweep.py` | NoC flit扫描入口；按目标实验协议使用 |

| `qwen_c16_rep1_hiband_ops.csv`、`qwen1_5_moe_full60_summary.json` | 根目录历史Qwen数据；应结合生成来源再引用 |

| `STATUS` | 根目录短状态文件；不能当作全项目科学验收 |



## 4. 工作副产物与受保护目录



`tmp/`、`_tmp_*`、`_docx_review_*`、`_todolist_review_*`、`_todo_review_render/`、`_qa_会议记录0924/`、`.codex_doc_review_260909/`、`.docx_review_260909/`、`.ppt_build/`、`_lad3d_ppt_build/`、`.tmp_clip3d_review/`、`.tmp_fg_check/`、`opportunity_docx_qa/`含渲染、解包、校对和构建材料。它们默认保留；自动清理可能删除唯一复核证据。



`.agents/`、`.codex-finalizer/`是本地工具/维护相关目录，本轮不改变其规则或运行内容。`.git/`是版本控制元数据，不纳入研究资产逐文件扫描；嵌套第三方仓库的`.git`同样排除。不复制凭据和用户级配置到汇总。



## 5. 清单生成与完整性边界



运行：`python tools/project_inventory.py`。该脚本只读取文件元数据，重写本目录的`asset_manifest.csv`和`asset_statistics.json`；不跟随符号链接/junction，不打开模型权重或Trace内容。



排除目录名：`.git`、`node_modules`、`__pycache__`、`.venv`、`venv`；排除本汇总输出目录以避免自引用。符号链接/junction和读取错误单独记录。统计使用字节数，不代表磁盘实际占用，不做内容去重或哈希认证。



这是本地快照：运行中的其他聊天可能同时增删文件，所以不是原子备份。外部D盘论文、微信附件、SERVER-113原始日志、压缩包内部文件和历史聊天下载链接仅作为依赖线索，不在“本地全部文件已核对”的范围内。全量清单只是覆盖元数据，未逐一验证所有资产语义。


## 6. 页级管理两阶段新增资产

| 资产组 | 目录/入口 | 当前用途与边界 |
|---|---|---|
| 管理价值审计 | `page_management_value_audit_v1/` | 先核对Sem-MoE/固定条带/独立页的比较对象；不是已证明胜原Sem-MoE |
| 第一阶段合同/原O核对 | `page_management_stage1_plan_v1/README.md`、`STEP1_RESEARCH_CONTRACT.md`、`STEP2_REPORT.md`（同目录） | 三策略分别对O主检验；O为项目RR前地址，不是作者地址 |
| 第一阶段静态输入 | `page_management_stage1_step3_inputs_v1/` | 六自然组完整表及历史标签绑定；当时O周期未有，后来步骤5已补齐 |
| 受控静态面板 | `page_management_stage1_step4_controlled_v1/` | 准备而非性能结论；后授权执行另目录保留 |
| 受控原生执行 | `page_management_stage1_step4_execution_v1/` | 108新原生/156逻辑行，预指定4/6达1%；Heat条件随机可复现、RR零增量 |
| 自然O原生补齐 | `page_management_stage1_step5_execution_v1/` | 6O+2RR身份，18比较7正11负，均未1%；本地约488MB归档范围见原验收 |
| 多seed随机统一对照 | `page_management_stage1_step6_execution_v1/` | 36不同随机+2身份成功，另保留失败前2RR；78逻辑行，约2.60GB/753成员验包按原报告 |
| 第一阶段总验收 | `page_management_stage1_step7_acceptance_v1/` | REPORT、ACCEPTANCE、EVIDENCE_MATRIX、SOURCE_MANIFEST；工作流完成/NO_PROMOTION，步骤7无新仿真 |
| 第二阶段原方案 | `page_management_stage2_plan_v1/` | 独立页相对强固定交织的假设、粒度和状态成本计划，预算不是已完成运行数 |
| 第二阶段合成S0停止 | `page_management_stage2_execution_v1/` | 固定C1相位达9槽下界，12静态全域表；新原生0，非自然无空间结论 |
| 自然V2方案/原审批历史 | `page_management_stage2_natural_v2/README.md`、`REPORT_BEFORE_APPROVED_EXECUTION.md`、`APPROVAL_BLOCK_BEFORE_APPROVAL.json`（同目录） | 原阻断保留，但已由AUTHORIZATION_AMENDMENT解除，不能继续等待授权 |
| 自然V2最终机器结果 | `page_management_stage2_natural_v2/FINAL_STATUS.json`、`INDEPENDENT_SUMMARY.json`、`LOCAL_ARITHMETIC_RECHECK.json`、`FINAL_INTEGRITY.json`（同目录） | 8case/98原生/140逻辑行，四worker修订后完成；REPORT已补齐NO_PROMOTION，140主布局行另12同址row对照；25日本地完整验包通过，收益状态不变 |
| 强固定包络/门槛/归因 | `page_management_stage2_natural_v2/DSTAR_FREEZE.json`、`INDEPENDENT_BRANCH_GATE.json`、`ROW_CONTROL_STATUS.csv`、`STATE_COST_LEDGER.json`（同目录） | D_star Q3 PHASE4/Q15 XOR4；强化BLOCKHASH4；无布局通过新来源门槛，ROW不可识别，净收益未验 |

## 7. 公式与选择器资产沿革

| 资产 | 当前解释 |
|---|---|
| `selector_all_moe_formula_v1/FINAL_FORMULA_REPORT.md` | 288独立层×组矩阵已完成，原式全部RR，收益0而非零后悔；16:15在途数仅历史 |
| `selector_all_moe_formula_revision_v2/` | 294完整块/78人工barrier分合同开发修订；独立区间与部署仍未通过 |
| `selector_all_moe_formula_revision_v3/` | 点选择84CA导致完整块总周期小幅增加，NO_PROMOTION，不更改默认 |
| `selector_exposed_conflict_formula_v4/` | 基础项+暴露冲突惩罚开发解释；完整块无增量，人工合同有排序收益但绝对误差仍大 |
| `selector_exposed_conflict_formula_v4/frozen_v1/` | 24受保护文件、FREEZE相对路径/manifest回执、静态推理入口/参数/数学Schedule；研究冻结非完整运行器 |
| `selector_address_formula_plan_v1/` | 旧自然二特征负结果与人工窗口MLP公式独立保留，不当新矩阵验收 |
| `selector_execution_objective_v1/frozen_strategy_v1/` | 旧受控17文件冻结继续保护，PASS仅旧受控执行目标 |
| `selector_real_holdout_v1/` | 历史第0层A/B选择准确但增量很小、规划60—150秒；A/B已用 |
| `selector_lightweight_delta_v1/`、`selector_lightweight_delta_revision_v2/`、`selector_lightweight_delta_revision_v3/` | 历史元数据路线失败/1秒失败，未因V4冻结自动修复 |

其余架构、DAG/信用/数值/命令后端、复现和历史布局目录逐项见[24日索引](REPORT_INDEX_20261024.md)及旧[22日审查](REVIEW_20261022.md)。原W4与BF16精度失败、不同热版本、阶段停止均保留，不将不同合同硬合并。

## 8. Challenge3批次与归档

- 最新Q1—Q3：[23日结果](../outputs/qwen_hotter_execution_20261022_v3/RESULTS_20261023.md)、RESULTS_AUDIT/RESULTS_EVIDENCE.zip；各256请求，峰温79.202837/79.293028/79.074963°C，未80/82/85。本批未重新筛查迁移合法冷目标，未执行策略。Q4仅静态候选，不在该批正式结果中。
- 此前I8/P1/P2/P3：[22日结果](../outputs/qwen_hotter_execution_20261021_v2/RESULTS_20261022.md)；P1/P2有7471/94离线独立任务机会，P3无源热机会。该准入不能自动继承Q1—Q3，也不是已执行次数。
- 此前首批CONTROL60/强度：[补跑完整四组](../outputs/qwen_control60_repair_20261021_v1/RESULTS_20261021.md)，最高77.8488°C；原OOM与3/4现场保留。
- 既有[本地约4.27GB全包](../outputs/qwen_hotter_full_archive_20261022_v1/README.txt)对应I8/P1/P2/P3，含远端14978载荷及364补充文件的归档记录，不等于Q1—Q3原始大文件已全部同包回传。归档只计压缩文件，不展开重复计数，恢复命令不自动执行。
- 第二阶段自然分支约7.45GB包已本地验收，1962载荷文件哈希/98运行绑定通过；见[最终交付](../page_management_stage2_natural_v2/DELIVERY_COMPLETE.json)。本维护不加载容器或接管其他聊天。

## 9. 历史、清单与工作区维护边界

原三文档全部补记和旧清单原字节见[25日更新前快照](history/before_20261025_update/snapshot_manifest.json)，20/21/22日快照和审查继续保留。目录名final、静态PASS、机器COMPLETE、文本REPORT、完整本地归档和工程NO_PROMOTION分别判断。

元数据盘点用`python tools/project_inventory.py`，只读内容之外的大小/路径/时间；排除Git、依赖/虚拟环境、链接目标、本维护输出目录。模型/Trace/压缩内容不逐项打开，不清理tmp/QA/构建/失败目录；外部D盘与未回传113原件不在全部本地文件范围。扫描非原子快照，不由文件数推实验完成数。


## 10. 10月25日辅助验证资产入口

| 目录 | 当前用途/边界 |
|---|---|
| [missing_workload_assets_113_20261025_v1](../missing_workload_assets_113_20261025_v1/REPORT.md) | 有界缺项搜索；历史R1—R7 CPU功能链 |
| [asset_completion_20261025_v1](../asset_completion_20261025_v1/REPORT.md) | 三元数据语义重建、完整DINO源码澄清；不恢复checkpoint身份 |
| [dino_fc1_v3_6_step3_20261025_v1](../dino_fc1_v3_6_step3_20261025_v1/REPORT.md) | 原FC1单NPU功能/原生事件有限验收 |
| [dino_contract_audit_20261025_v1](../dino_contract_audit_20261025_v1/REPORT.md) | 限定目录缺项、FC1/原ZIP分片合同只读复核；无TP16运行 |
| [olmoearth_v3_6_integration_20261025_v1](../olmoearth_v3_6_integration_20261025_v1/REPORT.md) | 同开发Block0单cluster原生适配与3倍MAC成本 |
| [olmoearth_v3_6_multi_npu_20261025_v1](../olmoearth_v3_6_multi_npu_20261025_v1/REPORT.md) | TP16/活动16-router子mesh有限执行；非gateway或动态HiBand |
| [olmoearth_collective_causality_20261025_v1](../olmoearth_collective_causality_20261025_v1/REPORT.md) | 原事件区间/中继因果审查；新增原生运行0 |
| [four_workloads_step3_cuda_20261025_v1](../four_workloads_step3_cuda_20261025_v1/REPORT.md) | 原R7 CUDA/G3原语句FP64功能；非目标平台性能 |
| [r7_g3_v3_6_integration_20261025_v1](../r7_g3_v3_6_integration_20261025_v1/REPORT.md) | R7 FP32/G3双FP32设备适配，保留普通FP32失败与CPUcodec成本 |
| [four_workloads_operator_graph_v3_6_20261025_v1](../four_workloads_operator_graph_v3_6_20261025_v1/REPORT.md) | 六个分合同结构图及查看器；交付回执优先于包内旧上传段落 |
| [radiometric_r1_r5_v3_6_20261025_v1](../radiometric_r1_r5_v3_6_20261025_v1/REPORT.md) | 历史有限R1—R5原生适配；R4软件比较归约分箱 |
| [radiometric_r1_r7_chain_20261025_v1](../radiometric_r1_r7_chain_20261025_v1/REPORT.md) | 新计算CPU/原生混合闭链；目标CPU/hostlink时序未耦合 |
| [geometric_g7_v3_6_20261025_v1](../geometric_g7_v3_6_20261025_v1/REPORT.md) | 原保存G6→新G7软件再入口；不含新G8或G0起全链 |



## 11. 10月26日候选与准备资产

| 目录 | 入口与状态边界 |
|---|---|
| [LingBot TI2V](../lingbot_ti2v_feasibility_20261026_v1/REPORT.md) | 固定源码/模型索引、最小协议、完整文件大小与选择性下载清单；DOWNLOAD_PROGRESS是后续在途观察，旧STATUS非当前交付结论 |
| [mini-SWE＋Qwen3](../mini_swe_qwen3_preflight_20261026_v1/README.md) | 预检/官方源码快照、113资源证据、模型元数据、共享区准备与恢复脚本；脚本存在不代表已运行完成，不自动执行 |
| [ScaleZero公开审查](../scalezero_public_audit_20261025_v1/REPORT.txt) | 固定源码归档、发布渠道与权重缺口；非免训练就绪 |
| [BEVFusion静态审计](../bevfusion_model_audit_20261025_v1/REPORT.md) | 全部3模型及15源码/头文件、完整图/哈希；非MoE辅助候选，不是执行/检测精度认证 |

26日更新前原字节见[7文件快照](history/before_20261026_update/snapshot_manifest.json)；25日及更早快照仍保留。新下载到113的权重不在本地元数据清单内。


2026-10-26 LingBot续传修订：旧本机转发下载已失败，现保留断点改113直连官方ModelScope，93源码Git blob通过，13:58仍DOWNLOADING；不依赖本机开机、排除refiner，最终验收未完成。见[续传报告](../lingbot_ti2v_feasibility_20261026_v1/RESUME_V2_REPORT.md)和[观察回执](../lingbot_ti2v_feasibility_20261026_v1/RESUME_V2_RECEIPT.txt)。


2026-10-26 LingBot哈希异常修复：已确认旧本机relay将HTTP502错误页写入3份权重；9区间73728B官方源补回后3/3全SHA通过，损坏原件保留，原通过文件未覆盖。v3改113直连并恢复剩余下载，refiner排除，最终完整性/权限尚未验收。见[根因与修复](../lingbot_ti2v_feasibility_20261026_v1/HASH_MISMATCH_ROOT_CAUSE.md)、[机器修复回执](../lingbot_ti2v_feasibility_20261026_v1/REPAIR_RESULTS.json)。


2026-10-27 LingBot交付收尾：已取回141文件69694390066B的最终哈希/索引/权限通过回执，当前209项mode检查0坏项、父ACL可遍历；refiner权重排除、无残余下载分片。未另账号登录测试，无推理/收益认证。此前在途状态为历史。见[完成报告](../lingbot_ti2v_feasibility_20261026_v1/DOWNLOAD_COMPLETE_20261027.md)。


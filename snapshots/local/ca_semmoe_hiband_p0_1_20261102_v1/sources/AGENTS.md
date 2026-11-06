# 跨层优化：全项目维护指南

2026-11-02 swe_qwen3[持有权/收尾v8](swe_qwen3_lifetime_owned_20261102_v8/REPORT.md)：完整两层CPU回放759投影/56阶段/12严格输出KV及3920分配回收独立通过；16项KV持有权变化防止读者归零后的提前释放。真实单活动端点两轮10子进程0、每轮51缓存门/33写回回执/32反馈，泄漏持有权明确拒绝；不是全层原生通过。[v5](swe_qwen3_continuous_cache_20261101_v5/REPORT.md)因动态库ISA准入缺口停止，非观察到数值失败；[v7](swe_qwen3_continuous_portable_20261101_v7/REPORT.md)完整可移植重跑仍运行，v8严格等待其最终通过后启动。原BF16/host128-HB8/GPU差异不改，1—7仍PARTIAL，无新GPU/SWE/物理或收益。

2026-11-02 LingBot[完整TP两轮检查](lingbot_step5_full_tp_20261101_v6/CHECK_20261102.md)：第一轮16rank双CFG98869查询及208590 NoC回放完成，独立core/O/FFN输入零差异；第二轮条件前43136行通过、无条件未开始。控制器及独立审计归档任务存活，无失败文件、未重启；最终两轮回执未生成，步骤5仍PARTIAL。MoE检查点拼接非连续全层时序，原混合BF16-FP32/host128-HB8/目标GPU0及门槛不变。

2026-11-01 LingBot[CPU成本样本](lingbot_step5_cpu_fda_20261101_v8/REPORT.md)及[真实CPU回调双轮](lingbot_step5_cpu_service_20261101_v9/REPORT.md)有限通过：Sniper执行单查询K/V及O末片，2304 FP32软件参考与BF16原GPU逐位通过；回调两轮各516时钟/217域记录/41水平PopNet，第二轮反馈全应用、10子进程0，94载荷SHA及补取原始CSV本地重算通过。仅单活动NPU/HB、非完整CPU成本/缓存维护认证。完整TP第一轮条件16头各24704行、50593792 BF16 core元素零差异，仍运行；步骤5 PARTIAL，原混合精度/host128-HB8/目标GPU0不变。

2026-11-01 LingBot[完整MoE两轮验收](lingbot_step5_full_ep_20261031_v5/COMPLETION_20261101.md)：每轮98869行/607451136边界元素逐位通过，84741主审计/160Bank检查、21536宏DAG节点/96880水平PopNet及全部第二轮反馈通过，66子进程0。原358成员包及补329成员包本地SHA通过，192数值数组4.86GB留113、525项SHA索引；本地重建DAG/Bank通过，非本地重算全量GPU数值。[完整TP attention/O](lingbot_step5_full_tp_20261101_v6/REPORT.md)已独立后台启动，16线程/nice10/24h上限、独立core首差观察及审计归档；新FFN全量一致才拼接已验收MoE检查点，非连续完整层时序。新K/V目标GEMM、CPU/PCIe/完整算子与SRAM成本及收益仍未认证；原BF16-FP32/host128-HB8/目标GPU0不改，步骤5 PARTIAL。

2026-11-01 swe_qwen3[布局/缓存有限验收](swe_qwen3_alias_cache_20261101_v4/REPORT.md)：布局CPU回归759矩阵/56阶段/12严格项通过、768来源缺口归零；新目录式DRAM完成标识及软件LRU逐出在真实Sniper小探针通过，3写回回执、约86.2ns模拟等待、后续CPU绝对时间晚于完成，跨集合3miss/不维护0miss。237成员2.11MB包本地SHA、原日志及SQLite独立通过；前4轮失败/诊断保留，202个旧容器依赖重绑后完整重编译。新缓存/别名尚未接回完整两层；动态释放/控制/完整时序和1—7仍PARTIAL，原BF16/host128-HB8/GPU差异不改，无新GPU/SWE/物理或收益。

2026-11-01 swe_qwen3[完整两层v3验收](swe_qwen3_continuous_lowering_20261031_v3/REPORT.md)：流式修订两轮真实统一入口完成，每轮759矩阵/32形状、374向量、4320 CPU软件调用；1626944个原始FP32元素、56阶段/12输出KV严格通过，98079水平PopNet反馈/70子进程通过。613成员128777679B安全包本地SHA及独立数值/时钟/依赖复核通过。v1/v2停止保留，旧v2运行中记录已过时。v3每轮768布局来源缺口仍保留；[隔离v4](swe_qwen3_alias_cache_20261101_v4/REPORT.md)新增HB读回别名登记及C跨步长地址服务，CPU控制回归759矩阵/56阶段/12严格项通过，缺口降为0，但目标原生0。缓存软件逐出已见脏行写回，完成队列屏障候选仍待原生验证；不把CPU回归或构建计作目标通过。原BF16/host128-HB8/GPU差异保持，缓存/控制/动态释放及完整时序仍缺，1—7PARTIAL，无新GPU/SWE/物理或策略收益。

2026-10-31 LingBot[步骤5连通层两轮](lingbot_step5_coupled_20261031_v4/REPORT.md)：真实16NPU/16HB，双CFG各64查询全KV上下文，保序O→自由router→owner专家重算→返回/层输出两轮逐位通过；22055数值传输/160Bank检查、每轮5774 DAG节点/1792水平PopNet及全部第二轮反馈通过，66子进程0，739载荷50.16MB本地SHA与194数组对逐位通过。v2竞态和v3主动停止保留，源兼容CPU数学/宏代理非完整opcode时序；[全98869行MoE子图](lingbot_step5_full_ep_20261031_v5/README.md)已通过门控后台启动，16线程/nice10/12h上限及独立审计归档，仍运行。目标GPU0/混合BF16-FP32/host128-HB8不改；完整TP attention、CPU/PCIe/完整SRAM成本及策略收益未认证，步骤5 PARTIAL。

2026-10-31 swe_qwen3[完整两层成本接入续版](swe_qwen3_continuous_lowering_20261031_v2/REPORT.md)：全759矩阵/32形状与CPU codec/norm/softmax/SiLU/Top8/route/gather/index_add/布局/KV服务已接回真实统一入口，10:44:53启动SSE隔离续版，最终数值/NoC审计仍运行。72组19404元素边界挑战非原生时序；全BF16域codec/SiLU及两层软件参考/6拒绝控制通过。16GiB全FP32指数+128KiB SiLU为模型无关host兼容数据，计128GiB容量/访存；源SLEEF依赖保留。CPU-only759矩阵1626944个FP32 oracle已生成，额外严格比对等待目标；117载荷快照本地SHA通过，非目标PASS。标量初轮主动停止/记录保留，未称数值失败；原BF16/host128/HB8/GPU差异不变，GPU/SWE0。Bank端口/条带为研究点，CPU缓存维护/控制/动态释放仍未认证，1—7PARTIAL；最终需DELIVERY_STATUS、RAW_ORACLE_AUDIT与SAFE_DELIVERY_STATUS，无收益结论。

2026-10-31 LingBot[步骤5固定通信首门](lingbot_step5_ep16_20261031_v1/REPORT.md)：双CFG790952次真实分配EP16序列化/槽位恢复及202483712个FFN BF16元素通过，1940条预定子集真实字节PopNet、12242独立检查及36载荷SHA通过。O分片FP32求和130/106差异保留，同输入逐rank FDA累加器传递零差异；尚未完整TP16或payload耦合NoC/DAG，容量仅静态，步骤5 PARTIAL。原精度/host128-HB8/目标GPU0，无策略收益。

2026-10-31 LingBot[步骤4有限功能收尾](lingbot_step4_native_repair_20261031_v6/COMPLETION_REPORT.md)：双CFG98869行单层CPU逐位一致及30944项独立审计通过；新5路split-K/FMA原生router行128 FP32与GPU/独立Windows标量逐位一致，75445检查/10283事件/33312事务及8载荷SHA通过。导入失败和计数失败保留；累计原生尝试3（新失败1/成功1），物理0/本轮GPU0。原BF16-FP32/host128-HB8不改；仅CPU单层功能及原生单行事件门，完整层目标lowering/时序、48层40步/VLM/VAE/TI2V及策略收益未认证。

2026-10-31 swe_qwen3[最终反馈/CPU与Bank续作](swe_qwen3_codec_fp32_sram_20261031_v1/REPORT.md)：完整16节点连续两层两轮PopNet均完成，419载荷本地SHA及独立数值/依赖/时钟通过，每轮56阶段/12输出KV、759矩阵/450远端/61fetch、28316水平反馈/433510时钟观测；非反馈收敛。新增真实Sniper CPU BF16 codec→设备FP32 primitive→实际4MiB/8Bank数据服务，M1及真实prefill专家16完整M6批量两轮分别768/4608个FP32和BF16逐位一致，本地独立NumPy复算及145/142载荷SHA通过。3Bank冲突/2拒绝控制通过，首次挑战构造失败保留；条带/单共享端口为显式研究点，CPU缓存维护时序未认证。新lowering尚未接回完整层，全部其余算子/DAG/完整时序仍待补，1—7PARTIAL；原BF16/host128/HB8、GPU差异及目标GPU0不改，无策略收益。

2026-10-30 23:18 swe_qwen3[完整16节点两轮phase1](swe_qwen3_legosim_16_layers_20261030_v3/README.md)：两轮各56阶段/12输出KV/CPU双回传及759矩阵（450远端）/61fetch已通过，第一轮全部28316条水平PopNet通过，第二轮回放运行中。最终独立审计/归档未结束，不认定反馈收敛；旧时钟错误的时序不晋级，原BF16/host128/HB8与GPU差异保留。完整CPU软件/算子lowering/SRAM Bank成本仍未覆盖，1—7PARTIAL，无策略收益。

2026-10-30 22:54 swe_qwen3[正确时钟下完整16节点phase1](swe_qwen3_legosim_16_layers_20261030_v3/README.md)：原BF16/host128/HB8，CPU2.5GHz tick与DRAM1.25ns换算修订。完整prefill19/cached decode1连续两层已实际通过56阶段/12输出KV/CPU双回传，759矩阵（450远端）/61host fetch及全部RPC权重输入输出SHA/last-reader通过，160载荷本地SHA和433510时钟观测通过；冻结索引另补取，原包不改。第一轮水平PopNet28316条仍回放、第二轮未完成，独立后台审计归档运行中；CPU/算子完整lowering及SRAM Bank/DAG仍缺，1—7PARTIAL。旧时钟错误的时序不晋级，旧数值/失败保持；GPU差异保留，无新GPU/agent/物理NPU或策略收益。

2026-10-30 swe_qwen3[16节点/通信时钟修订](swe_qwen3_legosim_clock_fix_20261030_v1/REPORT.md)：旧单NPU完整156105 PopNet与113载荷归档已通过；16节点首版功能通过但发现CPU2.5GHz tick误按1ns、DRAM1.25ns周期未换算，旧时序不晋级。隔离修订CPU clock_rate2.5、DRAM scale1.25及边界向上取整；真实16NPU/16×512MiB HB/host128文件后备两轮16门投影通过，每轮11296时钟观测/816NoC反馈，381载荷本地SHA通过。完整层v1缺worker清单失败、v2因时钟错误主动停止均保留。22:23启动[完整层v3](swe_qwen3_legosim_16_layers_20261030_v3/README.md)，prefill层0的14阶段对CPU源逐字节通过，其余层/decode/两轮回放仍运行；独立后台审计归档已启动，最终需读COMPLETE_DELIVERY。759矩阵/450远端/61fetch为预期非已完成数。原BF16/host128/HB8及GPU差异保持，新GPU/agent/物理NPU0；完整opcode/CPU软件/SRAM Bank及DAG仍缺，1—7PARTIAL，无收益结论。

2026-10-30 LingBot[步骤4稀疏专家修复/两阶段恢复](lingbot_step4_stagewise_20261030_v5/REPORT.md)：旧全查询在条件分支11776行后FFN4元素差异停止，失败保留。源专家28批量148的gate/up为6路split-K/FP32工作区；完整227328元素与GPU逐位一致，原失败64行FFN4→0（隔离诊断）。形状目录498项非498数值PASS，M142同核仍待全层门；SiLU全部有限BF16域一致。本轮3次有界外部GPU参考/完整模型0，累计v4-v5外部10；目标GPU0/新目标原生0/LingBot旧原生1/物理0。1660断点检查及4新负对照通过；仅复用11776行attention/FFN输入，旧专家输出不晋级。新流程先自主生成全部FFN输入再路由分组执行真实批量，113独立后台16线程/nice10/12小时上限并自动独立审计，仍PARTIAL；原BF16-FP32/host128/HB8与旧失败不改。41载荷8396965B复核包本地归档SHA通过；两次源码审批超时已由具体3882B包授权解决，当前无待审批项。

2026-10-30 16:37 swe_qwen3[完整两层FIFO修复版](swe_qwen3_legosim_integration_20261030_v1/CONTINUOUS_LAYERS_20261030.md)：真实统一phase1完整prefill19/decode1连续两层通过，CPU双结果逐字节核对且CPU_PASS存在、无EOF；56阶段/12严格输出KV、759权重版本/2998保留节点及7负对照，修复版98载荷本地SHA通过。三个phase1子进程0，156105条PopNet phase2正在运行，尚无完整层反馈/完整目标时序。原首轮EOF失败保留；单活动HB512MiB、原BF16/host128/HB8与GPU差异保持，1—7仍PARTIAL。

2026-10-30 swe_qwen3[完整两层统一入口续作](swe_qwen3_legosim_integration_20261030_v1/CONTINUOUS_LAYERS_20261030.md)：真实Sniper/NPUSim/外部Ramulator接入两层prefill19/decode1，首轮56阶段/12输出KV对CPU参考逐位一致，759次权重流、2998保留缓冲及7负对照通过；156105条PopNet回放完成。但CPU decode接收FIFO EOF，缺最终回执，首轮端到端FAIL，Sniper外层0不能代替验收。隔离持久写端修复版正重跑，结果需查DELIVERY_STATUS，不以启动视为通过。114本地载荷SHA通过。诊断HB RPC156101条不得计为规范水平NoC；单活动512MiB、host/PCIe/逐算子成本和显式DAG仍缺，1—7仍PARTIAL，原BF16/host128/HB8及GPU差异保留。

2026-10-30 swe_qwen3[统一工具链实际子链接入](swe_qwen3_legosim_integration_20261030_v1/PROGRESS_20261030.md)：源码授权后已上传/校SHA，隔离构建InterChiplet/PopNet；定位已有npusim_ramulator2_validation工作区，真实Sniper CPU＋NPUSim事件/payload＋外部Ramulator＋PopNet执行prefill19/decode1残差norm，38912/2048 BF16逐位通过，两轮加载315 delay。5个CPU ROI/5个NPU程序进程、7项失败验收负对照及1191载荷SHA通过，非完整层/KV或全16NPU。入口子进程失败传播/空phase2/旧delay拒绝在隔离修订通过，原源码保留。单活动HB512MiB，16×512MiB/host128仅静态绑定；完整权重后备/所有算子/完整时序未完成，第1—7步仍PARTIAL；旧342回退账本遗漏直接SiLU/路由等，不是完整算子覆盖。旧独立桥19不混计，物理NPU0/新GPU0；此前源码上传阻断已解除。

2026-10-30 LingBot[步骤4数值修复](lingbot_step4_bitexact_20261029_v4/REPORT.md)：原混合BF16/FP32、host128/HB8、目标GPU0。197738个rsqrt因子/404967424个postnorm元素、全序列12655232 logits与scores/98869行Top8/790952权重、全K/V404967424元素均对原GPU逐位一致；5路交错split-K、FDA16、Flash UNFUSE_FMA及原O bias精度边界修复。双CFG各64行串联attention→自主router/MoE→层输出10项1310720元素通过，67独立检查/12负对照、192载荷本地SHA通过。旧数学/GEMM/attention及遗漏bias失败保留。完整98869查询的单层CPU验收已在113独立后台启动，16线程/nice10/12小时上限、断点及首差即停，完成后独立复核；当前仍PARTIAL，不能把64行写成完整层或TI2V通过。16GiB EX2+64MiB RSQ指令域表是模型无关host软件兼容数据，另32MiB失败RCP候选保留，静态余约11.03GiB，访问/分页时序未认证。新增7次有界外部GPU参考、完整模型调用0；新目标原生0，LingBot累计旧原生1/物理0，无策略收益。

2026-10-30 swe_qwen3[Legosim统一入口核查/重排](swe_qwen3_legosim_integration_20261030_v1/REPORT.md)：已定位InterChiplet phase1/phase2入口；113旧树无NPUSim且入口缺Boost1.65，交付包具新模板，不能认定完整部署可用。BF16 codec/显式dtype存在，2-byte默认FP16；全局BF16不足以表达混合精度。904源码SHA核验，本地构建适配器/拒绝不完整启动的launcher与七阶段计划已备，未远端构建/未统一运行。源码上传113及编译被自动审批拒绝，等待本次具体源码包授权，未绕过；此前报告/审计上传授权不等同源码。旧累计19/Sniper3/物理0不变，原BF16/host128/HB8。

swe_qwen3跨日续作[FP32 softmax连续接入](swe_qwen3_softmax_primitive_20261029_v1/REPORT.md)：16路SLEEF显式数学依赖+C softmax流程接回两层，8调用40阶段、72控制712088元素、56阶段/12输出KV及交接/last-reader通过；127载荷本地SHA通过。exp阶段参考共享SLEEF，最终概率严格对未改torch.softmax，不是独立exp数学算法认证。8路候选与首次阶段oracle失败保留；本轮原生失败1/成功1，累计19/Sniper3/物理0，无新GPU/agent/留出/NoC。host回退350→342非性能结论，原BF16/host128/HB8，GPU GEMM与softmax FP32差异保留，步骤3PARTIAL，非TP/EP或完整时序。

2026-10-29 swe_qwen3新增[FP32 norm接回连续两层](swe_qwen3_norm_20261029_v1/REPORT.md)：独立C cascade8归约、sqrtf倒数及BF16归一化取代host norm求值；16次调用64阶段、72控制项3489018元素、56阶段/12输出KV、374向量节点通过；交接/KV/last-reader审计及106载荷本地SHA通过。138171事件/107954664事务、SRAM703744 B，host回退398→350非收益；norm宏codec/控制时序未全计，有限128/2048维CPU语义，非GPU norm或纯NPU认证。原BF16/host128/HB8，GPU GEMM及softmax FP32差异保留，步骤3PARTIAL；累计原生17/Sniper3/物理0，本轮GPU0。

2026-10-29 swe_qwen3新增[连续BF16向量原语](swe_qwen3_continuous_vector_20261029_v1/REPORT.md)：新C残差/RoPE及BF16乘加入口接回两层prefill19/decode1；12输出/KV、56阶段、374向量节点逐位通过，131072元素独立C挑战通过。2次连续HB交接/4次KV追加与last-reader审计通过；139081事件/108211456事务，SRAM703744 B。host回退772→398，非耗时收益；92载荷本地全SHA通过。累计原生16（含此前独立向量片段1）、Sniper3/物理0，无新GPU/agent/留出/NoC；BF16/host128/HB8，GPU GEMM及softmax差异保留，步骤3仍PARTIAL，非纯NPU/TP-EP/完整时序。补充审计状态上传已获批准并完成。

LingBot步骤4续作（2026-10-29）：[报告](lingbot_step4_completion_20261028_v3/REPORT.md)仍PARTIAL、未完成。独立C BF16专家软件核935阶段/5898240元素及两CFG记录路由MoE对单线程CPU源逐位一致，4线程295失败保留；适配器未知几何/bias/特殊函数显式拒绝。197738行H2048 mean(square)对原GPU FP32逐位一致，但正确RNE rsqrt因子41631不同、postnorm仍1314 BF16差异；给定GPU exp的12655232个score加除及后处理通过，不是自主sigmoid。exp2替代候选7权重差异保留；旧GEMM/attention/全层未过。532项独立审计/12负对照及281载荷本地SHA通过；新增1次外部数学参考约1.64GB峰值、完整模型调用0，目标GPU0/新原生0/物理0，LingBot原生累计1，host128/HB8与原混合精度不变。

## 10月28日维护事实基线（取代此前当前状态，历史范围保留）

维护日期：2026-10-28。原BF16/混合BF16-FP32、host128 GiB/HB8 GiB为显式研究配置，原host8规范未改；目标GPU为0，外部GPU参考与模拟器运行分别计数。以下不构成完整系统时序或HiBand/Sem-MoE/BDPL策略收益通过。

| 主线 | 当前完成范围 | 未通过与适用边界 |
|---|---|---|
| LingBot真实采集 | [步骤3报告](lingbot_step3_capture_20261028_v1/REPORT.md)：3936路由及共享调用，完整40步3840条、28完整fixture；31568项审计及6负对照通过，单步开关及此前40步latent逐位一致 | 已见example_4，非独立留出；采集完成不是目标全层功能通过。约9.68GB采集载荷留113，本地仅compact review，72载荷，不是全量回传 |
| LingBot router修复 | [步骤4 v2](lingbot_step4_router_repair_20261028_v2/REPORT.md)：同GPU scores的98869行Top8槽位及790952个BF16权重逐位一致；309项独立审计通过 | 同logits后CPU sigmoid仍6权重差异，自由GEMM/sigmoid仍93；完整上下文64查询/串联block仍有差异。两版各43比较13一致/30差异，不能宣称完整层PASS；1次原生FP32行对顺序参考一致、对GPU121/128不同。总体PARTIAL |
| swe_qwen3连续两层 | [四项门槛](swe_qwen3_step3_four_gates_20261028_v1/REPORT.md)：68项前半层检查，258组645120元素batch核对，两层19-token prefill/1-token decode的4输出及8 KV严格项通过；2次连续HB交接、4次KV追加 | N0串行矩阵/存储与772次显式host回退；host成本null，非纯NPU、TP16/EP16或完整时序。139420事件/107915094事务、SRAM703744 B/HB范围102833632 B为本合同。累计原生14、Sniper3、物理NPU0；不把历史各片段重复求和 |
| swe_qwen3 prefill定位 | [首差异报告](swe_qwen3_prefill_first_difference_20261028_v1/REPORT.md)：内部首差为input RMSNorm FP32 mean(square)9行，但回BF16消失；首次持续BF16差为同输入Q/K/V GEMM74/5/3元素。50阶段/100二进制绑定旧路径 | 定位非修复。原4249输出、10路由slot及softmax FP32差异保留；10 slot含9同集合换序与1边界平局换专家，不能全部归因QKV。仅1次有界外部GPU前半层诊断，未重跑完整层、无新增目标原生 |
| agent验收 | [冻结留出](swe_qwen3_step3_holdout_20261026_v1/REPORT.md)：两开发及两Astropy留出均未修复，留出0/2、空补丁；采集/证据工作完成 | 不是总体成功率，也不是agent就绪。已用留出不得重称未见；[v2/v3复核](swe_qwen3_step3_progress_20261027_v3/REVIEW_20261027.md)仍官方未过，重复同两开发非独立样本。v4 README/启动记录不能替代最终官方评分；本轮未确认其功能准入 |

归档与授权：LingBot采集完整数据、router两版约3.13GB输出留113，本地分别为72载荷/297成员review子集，原任务回执核SHA不等于本维护重验全量。swe留出约1.56GB包307载荷、连续两层260载荷及首差异本地审计按对应报告范围保留。首差异报告已记录用户批准后旧报告上传113并核SHA；此前上传拒绝、留出正文拒绝均为历史，不再写成当前同一操作阻断。旧第二阶段7.45GB/Q1—Q3本地20文件交付沿用原回执，无新增网盘上传证据。

四负载继续为非MoE辅助验证资产，旧有限功能/原生事件结果不撤销，不进入MoE核心机制收益证明。新两MoE路线已经超出26日“未下载、未采集、原生0”阶段，但完整目标时序与实际策略净收益仍未建立。采集、CPU一致、GPU一致、原生事件因果与净收益分别验收。

本轮仅核对本地上述原报告及两专责聊天最近3轮；非全分页重读，不更新其余聊天读取日期，不连接113、不运行实验、不重验大型载荷。源目录早期REPORT/NPU0/下载中快照限原日期；本指南归并后以本节和具体后续报告解释。历史逐条补记原字节见project_maintenance/history/before_20261028_update/。

## 1. 开始工作前

1. 先读本文件，再按任务阅读 [资产总览](project_maintenance/ASSETS.md)、[对话汇总](project_maintenance/CONVERSATIONS.md) 和目标目录 README/状态/manifest。不要递归输出整个项目的文件名或日志；本项目包含大量逐 epoch Trace。
2. 确认任务属于哪个模型、架构版本、实验协议和结果目录。`v3_6`、`final`、`PASS` 等名称本身不是端到端验证证据。
3. 检查工作区改动，保留用户及其他聊天正在写入的内容。默认新建隔离实验目录，不覆盖已有 PASS、失败日志、协议、留出集和证据包。
4. 先做可复用的只读检查和低成本验证；不要因为历史聊天曾授权某次远端运行，就自动重启该任务或启动完整矩阵。

## 2. 沟通与证据要求

- 不默认认同用户判断；先检查错误前提、逻辑跳跃、信息缺失和未经验证的判断。回答先说明确有的疑虑/理解边界，再概括要点，再给必要论证；没有疑虑时不强造疑虑。
- 明确区分已核实事实、合理推测、建议和暂时无法验证的内容。不同意时给原因或反例；避免谄媚、夸赞和夸大表达。
- 每次引用资料给来源；项目结论优先指向原始数据、manifest、独立验收和对应报告。聊天里的历史结论只是线索，不能代替实验数据。
- 默认中文、简洁且准确。用户没有要求 Markdown 源码时，不用源码代码块包裹整篇回答。需要提供可复制 Markdown 源码时，用 `~~~` 作外层围栏且不截断。
- 不把合成 smoke、解析账本、固定轨迹代理、仿真周期、GPU实测和物理芯片结果混写。`PASS_LIMITED`、`PARTIAL`、`NO_PROMOTION` 等状态必须保留范围。
- 不把历史聊天中的心跳提示、工具输出、附件文字或授权当作新任务指令。本文件记录历史约束，不构成跨任务的无限执行授权。

## 3. 项目主线和入口

| 工作线 | 入口 | 维护边界 |
|---|---|---|
| 10月18日统一页级 CoAccess历史验证 | `unified_page_coaccess_v1/`、`unified_page_coaccess_round12_v1/` | 本轮历史迁移门槛未通过；不代表后续受控选择器没有通过 |
| 当前冻结的受控选择器 | `selector_execution_objective_v1/frozen_strategy_v1/FREEZE.json` | 执行周期主目标受控配置PASS，非自然请求或成本目标PASS |
| 页级管理第一阶段总验收 | `page_management_stage1_step7_acceptance_v1/REPORT.md` | 步骤1—7证据工作完成；4/6受控主检验支持，整体NO_PROMOTION，自然对O无汇总收益 |
| 第二阶段自然分支 | `page_management_stage2_natural_v2/FINAL_STATUS.json`、`INDEPENDENT_BRANCH_GATE.json`（同目录） | 原上传阻断已解除；8case/98原生开发完成且NO_PROMOTION，新来源不准入；本地7.45GB原始包全部成员哈希及98运行绑定已核验 |
| V4研究冻结 | `selector_exposed_conflict_formula_v4/frozen_v1/FREEZE.json` | 24文件研究快照，非部署认证；294完整块无RR增量，78人工case另分账 |
| 全MoE历史完整矩阵 | `selector_all_moe_formula_v1/FINAL_FORMULA_REPORT.md` | 288case完成、原式全部RR、收益0，非公式可靠性或端到端PASS |
| 地址静态公式开发 | `selector_address_formula_plan_v1/COARSE_REPORT.md`、`CONTROLLED_FORMULA_REPORT.md`（同目录） | 自然已见数据无增量；人工排序与误差带另列，非通用延迟公式 |
| 历史第0层真实块级选择器 | `selector_real_holdout_v1/REPORT.md`、`METHODOLOGY_FROZEN.md`（同目录） | A/B单MoE块选择通过；路由已知、成本未达标、A/B已使用 |
| 历史轻量元数据路线 | `selector_lightweight_delta_revision_v3/REPORT.md` | 步骤5字节正确，API超1秒；步骤6—7/拟合未执行 |
| Challenge3热主线 | `outputs/qwen_hotter_execution_20261022_v3/RESULTS_20261023.md` | Q1—Q3各256完成，峰温79.075—79.293°C，未80/82/85；本批未重筛迁移准入，无策略收益 |
| WHISPER CoAccess 正式对照 | `whisper_coaccess_v1/FINAL_REPORT.md` | 已完成矩阵，未显示相对 round-robin 的周期增量 |
| 2026-10-13 两模型布局总结 | `COACCESS_BANK_LAYOUT_QWEN3_QWEN15_REPORT.md` | 是此前阶段结论；不得覆盖后续真实页时间留出验证 |
| WHISPER 工作负载与工具链 | `whisper_operator_inventory/README.md` | 实测 hook、结构补全、控制节点要保留来源分类 |
| V3.5 可执行 WHISPER 基线 | `whisper_operator_inventory/target_architecture_v3_5/README.md` | NoC + DeepStack per-bank DRAM；排除绝对热执行 |
| V3.6 规范架构 | `whisper_operator_inventory/target_architecture_v3_6/README.md` | 配置就绪不等于整体执行验证；overlay单独标注 |
| OLMoEarth V3.6 TP16 | `olmoearth_v3_6_multi_npu_20261025_v1/REPORT.md`；`olmoearth_collective_causality_20261025_v1/REPORT.md` | 同开发Block0的16 NPU原生适配/活动NoC子mesh有限通过；新增只读区间/中继因果审查，无新运行或中间归约数值认证；非物理性能、gateway或动态HiBand认证；保留单cluster与失败 |
| 三负载缺项搜索/R1—R7闭链 | `missing_workload_assets_113_20261025_v1/REPORT.md` | 有界搜索未找回新匹配资产；原输入R1—R7 CPU功能闭链11项逐位通过，非GPU/V3.6；DINO全块/R8—R10/几何仍阻断 |
| 原元数据恢复/源码同一性 | `asset_completion_20261025_v1/REPORT.md` | 从原记录重建几何affine/window/NoData三个小文件，G7/G8新导出有限通过；非原文件SHA找回。DINO已有完整维度独立CUDA校验源码，主入口仍缩减；官方源码同结构不证明同权重 |
| DINO真实FC1原生执行 | `dino_fc1_v3_6_step3_20261025_v1/REPORT.md` | 原FP16 fixture在N0/CH0完成计算/32 B事务/容量/依赖有限验证，单倍MAC；非完整Block0、NoC或物理性能，整体第3步仍PARTIAL |
| DINO专责合同复核 | `dino_contract_audit_20261025_v1/REPORT.md` | 113限定目录20输入/参数及19阶段Golden仍缺；原FC1绑定/输出与原ZIP16分片SHA交叉核验通过，仅静态切分，无新模型或NoC执行，完整块仍阻断 |
| R7/G3原CUDA功能覆盖 | `four_workloads_step3_cuda_20261025_v1/REPORT.md` | H100上原R7源码及G3原代码片段数值通过；2路径6配对比较，非原融合G3/G4或目标V3.6系统/性能认证；原资产缺项不解除 |
| R7/G3 V3.6设备适配 | `r7_g3_v3_6_integration_20261025_v1/REPORT.md` | R7 FP32设备阶段通过；G3直接FP32失败、FP32双数软件适配通过，非原生FP64。CPUcodec/PCIe/NoC时延未耦合，成本单列，仍非完整流水 |
| 四负载算子图/架构映射 | `four_workloads_operator_graph_v3_6_20261025_v1/REPORT.md` | 六个分合同DAG绑定V3.6与既有有限执行；参考两会话方法总结，源码/缺项/失败分开。仅结构交付，无新负载运行，第3步仍PARTIAL |
| 辐射R1—R5历史适配 | `radiometric_r1_r5_v3_6_20261025_v1/REPORT.md` | 原输入N0/CH0功能/原生事件有限通过，10项逐位一致；R4为FP32比较归约软件直方图，非原生U32原子。CPU阈值/hostlink时延未耦合；1623旧文件不变，完整四负载仍PARTIAL |
| Qwen1.5 HiBand/Sem-MoE | `qwen1_5_moe_a2_7b_v3_6/README.md`、`qwen_hiband_scope_fix/` | 合成路由、真实路由、memory-stress负载分开报告 |
| Qwen3-30B 执行与诊断 | `qwen3_30b_a3b_v3_6_experiment/` | 地址压力/paging、full trace、关键路径归因分开 |
| 解析映射 | `qwen3_8b_v3_5_mapping/`、`qwen3_30b_a3b_v3_5_mapping/`、`qwen1_5_moe_a2_7b_v3_5_mapping/`、`qwen1_5_moe_a2_7b_v3_6_mapping/` | 不等于模拟器已执行 |
| HiBand 独立参考复现 | `hiband_reproduction/STATUS.md` | 非作者完整artifact，不能宣称论文数值复现完成 |
| DeepStack AE | `DeepStack_official_ae/README.md` | 独立环境和工作流；本次维护未重跑复现 |
| PIMoE | `PIMoE_reproduction/PIMoE_复现全过程与结果说明.md` | 直接测量、仿真、论文估算和解释性算法修正分开 |
| 机器人应用 | `RobotAPP_upload/README.md` | SLAM、Whisper资产；本次维护未补证π0.5端到端接入 |
| 论文和报告 | `paper_261010_stage/`、`outputs/`、根目录 PPTX/DOCX/PDF | 工作副本与外部论文主目录不能混淆 |
| 辐射R1—R7混合闭链 | `radiometric_r1_r7_chain_20261025_v1/REPORT.md` | 新R5→原R6 CPU→新R7，22项逐位一致；CPU/hostlink目标时序未耦合，R8—R10仍缺项 |
| 几何G7再入口 | `geometric_g7_v3_6_20261025_v1/REPORT.md` | 原保存G6输入上的新软件lowering有限通过，非G0起全链；G8本轮未跑 |

| LingBot真实MoE TI2V候选 | `lingbot_operator_graph_v3_6_20261027_v1/REPORT.md`、`EXPERIMENT_PLAN.md`（同目录） | 141文件源码/基础模型下载与Unix权限通过；结构图/候选映射已交付，精度/容量与真实推理仍未验收；refiner排除 |
| mini-SWE＋Qwen3 MoE候选 | `mini_swe_qwen3_preflight_20261026_v1/README.md`、`REMOTE_RESOURCE_REPORT.md`（同目录） | SSH恢复、资源只读核查；后续逐分片复制未获本地最终回执，依赖/任务/自主路由未通过 |
| 非MoE候选排除/公开交付审查 | `bevfusion_model_audit_20261025_v1/REPORT.md`、`scalezero_public_audit_20261025_v1/REPORT.txt` | BEV全部模型静态排除MoE；ScaleZero有结构但未找到匹配公开checkpoint，二者均无新增性能准入 |

## 4. 截至10月26日的历史事实基线（28日状态见前文）

本次核对本地报告、机器回执和8条聊天的分页记录，未连接113或启动/推进/终止实验。具体时间点不一致时，以同合同的后续验收/交付修订为准；旧报告及失败不改。更新前7文件见[历史快照](project_maintenance/history/before_20261026_update/snapshot_manifest.json)，纠错及范围见[维护审查](project_maintenance/REVIEW_20261026.md)。

### 10月26日历史选择与准入状态

选择已明确，执行验收尚未完成：“推荐HiBand与Sem-MoE负载模型”对话最终选择LingBot-Video-MoE-30B-A3B的基础TI2V视频负载，以及mini-SWE-agent＋SWE-bench Lite、现有Qwen3-30B-A3B MoE后端。两条专责聊天已建立。本维护只读取历史，不创建新聊天、不接管后台资产任务；“选为benchmark”只表示进入验证，不是可运行认证或HiBand/Sem-MoE/BDPL收益通过。

| 候选/路线 | 当前证据与定位 | 阻断、历史修订及收益边界 |
|---|---|---|
| LingBot基础TI2V | [盘点](lingbot_ti2v_feasibility_20261026_v1/REPORT.md)、[最小协议](lingbot_ti2v_feasibility_20261026_v1/MINIMAL_PROTOCOL.md)：固定源码dd5c231e、权重修订f2e538f6，48层/128 routed experts/Top8＋1共享专家；公开视频推理入口及真实router可追溯。基础模型/文本编码器/VAE/源码清单约69.69GB，不含refiner | [后续下载观察](lingbot_ti2v_feasibility_20261026_v1/DOWNLOAD_PROGRESS.json)已是DOWNLOADING_CONFIRMED_NOT_COMPLETE，早期REPORT/STATUS的“未下载/SSH别名失败”是前一阶段快照。只记录最后可读观察，不认定进程此刻仍存活或下载完成；本地未取得最终验收回执。依赖、单/双卡内存拓扑与推理仍未验收。是视频生成基座，非机器人动作闭环；无真实路由采集/模拟器/策略收益结果 |
| mini-SWE-agent＋Qwen3 MoE | [预检与草案](mini_swe_qwen3_preflight_20261026_v1/README.md)、[后续只读资源报告](mini_swe_qwen3_preflight_20261026_v1/REMOTE_RESOURCE_REPORT.md)：SSH已恢复；现有16权重分片约61.07GB，config/index哈希与历史一致。后续专责聊天记录源码已校验，正在逐分片核验/独立复制至`/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1` | 只读报告未重算61GB全分片SHA；后续复制完成需该远端目录STATUS.state=COMPLETE_VERIFIED及成员/权限清单，当前本地无此最终回执，不能写已验收。该复制任务仅源码/模型，不含SWE任务数据、镜像和推理依赖。模型兼容性/命令闭环、任务修复、真实prefill/decode路由采集和目标平台执行均未通过，任务/推理/仿真仍为0 |
| ScaleZero | [固定提交公开交付核查](scalezero_public_audit_20261025_v1/REPORT.txt)：MoE实现和训练配置存在 | 在所查公开渠道未找到匹配的训练后checkpoint；不是全网不存在证明。Atari eval示例默认未启用相应MoE、权重占位且含训练更新，不是免训练即用负载。此前“结构候选”推荐收紧为暂缓近期正式准入，无训练/推理或收益 |
| BEVFusion | [固定提交静态审计](bevfusion_model_audit_20261025_v1/REPORT.md)覆盖15份非build源码/头文件和全部3个ONNX/ORT模型，关闭检测头结构未知项 | TopK选200个检测候选，Softmax为注意力，非专家路由。排除MoE核心benchmark，仅可保留通用算子/NoC/布局扩展候选；静态结构检查不是数值或执行认证，不覆盖旧build二进制。BDPL当前MoE/tile合同和拟合参数不能原样搬用 |
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

[第二阶段本地回执](page_management_stage2_natural_v2/DELIVERY_COMPLETE.json)继续记录约7.45GB、1962载荷文件/98运行绑定已验收；[Q1—Q3本地归档](outputs/qwen_q1_q3_full_archive_20261024_v1/LOCAL_SAVE_REPORT_20261025.md)为20文件5351897685 B，含对应镜像/依赖，未取得百度网盘上传的新回执；[四负载图谱](four_workloads_operator_graph_v3_6_20261025_v1/DELIVERY_COMPLETE.md)此前后续明确授权交付113成功，包内上传拒绝是历史。它们均不证明新LingBot/mini-SWE模型资产已完成交付。44.17MB代码ZIP传113也不是模型运行或性能认证。

本轮只核对本地报告、机器清单及分页对话，不连接113或重读数GB载荷；旧验包数量归于原任务回执，下载当前存活/完成状态暂不能独立验证。保留源报告的早期快照与失败，不改其受保护内容；本维护的新索引负责给出分阶段解释。

### 四负载：辅助验证资产，完整系统仍未认证

最新“分析新负载算子切分”对话已明确：四负载退出MoE机制收益的核心benchmark，保留为算子、访存、NoC与映射工具链的辅助验证资产。DINOv3和已核对OLMoEarth Block0是稠密Transformer；遥感辐射/几何是传统数值流水线，不能笼统称四个稠密神经网络。四者没有可用的MoE专家路由，Sem-MoE记N/A；不新增合成专家冒充真实MoE。此为研究定位调整，不撤销已有有限验收，也不授权本维护继续实验。

| 负载/合同 | 已确认的最新范围 | 仍未认证或阻断 |
|---|---|---|
| DINOv3 | [真实FC1](dino_fc1_v3_6_step3_20261025_v1/REPORT.md)原FP16 fixture在N0/CH0完成分块功能、32 B事务、容量/依赖验收；843055104 MAC为单倍。两参考在0.01+0.01×绝对参考值容差内，最大绝对误差1.0/1.4173583984375，非逐位一致。[合同复核](dino_contract_audit_20261025_v1/REPORT.md)另核原ZIP16分片SHA | 完整Block0同源20项输入/参数和19阶段Golden仍缺；完整维度校验源码已存在，不能再称全块源码不存在。TP16仅静态列切分，未运行DINO多NPU/NoC；FC1外部输入不能由shape相同推定为完整LN2输出 |
| OLMoEarth | [单cluster](olmoearth_v3_6_integration_20261025_v1/REPORT.md)与[TP16](olmoearth_v3_6_multi_npu_20261025_v1/REPORT.md)为同一开发Block0；TP16完成33项数值检查和活动16-router子mesh的2880消息、180 MiB原生通信门控；补偿实际32614907904 MAC为逻辑3倍。新增[区间因果审查](olmoearth_collective_causality_20261025_v1/REPORT.md)只读，无新原生运行 | 不含CPU gateway、逐SRAM Bank仲裁、校准特殊函数/物理性能或动态HiBand；中间FP32归约数组未保存，不宣称逐项重验部分和。54,412,064 TP16代理周期与单cluster523,345,780周期不构成完整系统加速认证 |
| 辐射校正 | [R1—R5](radiometric_r1_r5_v3_6_20261025_v1/REPORT.md)后又完成[新R1—R7混合闭链](radiometric_r1_r7_chain_20261025_v1/REPORT.md)：原DN重算R5→原R6 CPU→新统计发布→R7原生适配，22项配对逐位一致、17583事件/31205依赖；不是复用旧R6输出。原[R7 CUDA](four_workloads_step3_cuda_20261025_v1/REPORT.md)功能证据保留 | R4为显式计费FP32比较/归约软件直方图，非原生U32原子；R6发布为CPU语义翻译，非原InterChiplet通信。设备8046542周期不含目标CPU/PCIe/gateway；R8—R10各自原fixture仍缺，完整应用PARTIAL |
| 几何校正 | [G3双FP32软件适配](r7_g3_v3_6_integration_20261025_v1/REPORT.md)通过原严格容差，普通FP32的77823/81920超限失败保留；29 FP32原语/逻辑乘法及CPUcodec成本单列。[新G7再入口](geometric_g7_v3_6_20261025_v1/REPORT.md)以保存G6为输入，五项检查、390原生事件有限通过 | 不是原生FP64；未连接G3→缺参G4→G6，也未在新G7轮执行G8。原4096像元全有效，无效分支无原样例覆盖。RPC/DEM/query/FP64 NoData/源影像/G2原代码配置/可靠CRS仍缺，完整几何链阻断 |

这些原生适配的数值函数实际在服务器CPU求值，由NPUSim/Ramulator完成事件、SRAM生命周期或PopNet回调门控；“原生”指模拟器事件/库，不是物理NPU执行或原未改耦合二进制认证。局部32 B桥通过不修复旧256 B ABI路径。聚合SRAM容量通过不等于8个SRAM Bank仲裁通过。四负载完整第3步仍PARTIAL，尚无完整系统性能或净策略收益认证。

### 缺失资产、恢复与交付

- [有界搜索](missing_workload_assets_113_20261025_v1/REPORT.md)未找到新的匹配缺项，不能推出整台服务器不存在；其CPU R1—R7功能闭链11项是历史阶段，后续混合闭链22项另有新报告，不混计为独立样本。
- [元数据恢复](asset_completion_20261025_v1/REPORT.md)从原记录重建affine/window/U16 NoData三个文件共74 B，并有G7/G8导出检查；这是语义重建，不是找回原文件SHA。完整DINO源码存在不代表权重/输入身份恢复；官方同结构源码也不能证明同checkpoint。
- [四负载图谱交付](four_workloads_operator_graph_v3_6_20261025_v1/DELIVERY_COMPLETE.md)已获后续明确授权，113新目录50成员、49份产物哈希通过。包内REPORT的“上传拒绝/未上传”保留为批准前快照，当前以REMOTE_DELIVERY回执为准；结构交付不新增负载运行。
- [第二阶段交付](page_management_stage2_natural_v2/DELIVERY_COMPLETE.json)与[本地验包](page_management_stage2_natural_v2/LOCAL_ARCHIVE_VERIFICATION.json)记录7449703197 B、1963成员（1962载荷文件）、98运行及142输入集绑定通过；“回传中”已是旧状态。归档完整不改变NO_PROMOTION/NET_UNVERIFIED。
- [Q1—Q3完整本地归档](outputs/qwen_q1_q3_full_archive_20261024_v1/LOCAL_SAVE_REPORT_20261025.md)完成于25日：主包15735成员、P1依赖1470、本地补充198项；UPLOAD_TO_BAIDU共20文件5351897685 B，已验包，未上传百度网盘。旧4.27GB包仍只覆盖I8/P1/P2/P3；新包无Q4，不新增热策略结果。

上述载荷验包数量取自对应任务的本地报告/机器回执。本维护仅核对报告与小型证据清单，不重新遍历数GB归档内容，也未连接113、启动/终止实验或上传。


### 4.1 当前状态总表

| 主线 | 已完成/已确认 | 未通过、阻断或未知 |
|---|---|---|
| 第一阶段三策略对O | 总验收工作完成，受控主检验4/6达到冻结1%，自然O/随机比较齐备 | 整体COMPLETE_PHASE1_REVIEW_NO_PROMOTION；自然三策略模型内汇总均慢于O，Heat=RR，无净部署收益 |
| 第二阶段自然分支V2 | 原审批阻断已解除；本地FINAL_STATUS与独立汇总记录8case、98原生、140逻辑行完成 | 两模型开发准入均未过，新独立来源0；ROW归因NOT_IDENTIFIABLE、NET_UNVERIFIED；REPORT在24日维护期间已补齐NO_PROMOTION，完整本地交付验包已通过，见4.3新增收尾记录 |
| 公式V4 | 研究冻结24文件，数学定义/块级流程/静态评分入口齐备 | FROZEN_RESEARCH_ONLY_NO_PROMOTION；完整块无RR增量、绝对延迟精度未过，非集成运行器 |
| Challenge3 Q1—Q3 | 各256请求、8槽32代完整，保存轨迹审计通过，均越78°C | 未达80/82/85°C；未在本批重筛冷目标，非实际策略收益；Q4不在正式批次 |

### 4.2 第一阶段总验收：执行完成，不是三策略全部有效

来源：[总验收](page_management_stage1_step7_acceptance_v1/REPORT.md)、[ACCEPTANCE](page_management_stage1_step7_acceptance_v1/ACCEPTANCE.json)、[统一78行周期表](page_management_stage1_step6_execution_v1/UNIFIED_CYCLES.csv)。

- 研究合同分别检验RR、Heat、CA相对同一O，不是逐case事后挑三者oracle。自然O是项目分配器RR前地址，人工O_fixture单列；二者均不能说成作者Sem-MoE的完整地址/系统。Sem-MoE不应被笼统称为“无分页连续布局”。
- 受控步骤4完成108新原生、156逻辑行。6预指定工程检验仅4项达到1%：RR的R场景两模型0增量；Heat eA对O_fixture约18.6761%/59.0228%，CA eC约34.1078%/38.8112%。Heat与其条件随机同周期，CA对随机均值仍有约14.5902%/4.7102%。只支持人工合同的有限存在性。
- 自然步骤5补齐6个O，18逻辑比较7正11负、0达到1%；去除Heat=RR为12项4正8负。old/A/B均是已见第0层完整目标FP16块，ctx512、一次cached decode、四请求组，非新独立来源或全模型。
- 步骤6补36不同随机原生、54随机标签，与O/RR/Heat/CA组成78逻辑行。成功控制器38原生（36随机+2身份），另保留兼容性失败前2RR，共40；步骤4—6合计156次新原生，不能当156独立样本。步骤7只复核/归档，不新增仿真。

| 模型 | 策略 | 相对O周期加权收益 | 相对各自条件随机收益 |
|---|---|---:|---:|
| Qwen3 | RR/Heat | −0.002067% | +1.437832% |
| Qwen3 | CA | −0.061756% | +3.088361% |
| Qwen1.5 | RR/Heat | −0.003725% | +0.271523% |
| Qwen1.5 | CA | −0.265550% | +23.848720% |

负值表示更慢。所有18项均优于各自条件随机均值，但三策略相对O的模型内汇总全部略慢，CA也未在三组周期和上优于RR。随机继承完整改动集合、活跃/不活跃目的frame池；不是全空间均匀无信息随机。各策略匹配池不同，不直接用随机收益大小排序策略，更不能把优势全归因Bank冲突。

工程收益、画像贡献和归因仍未建立：Heat=RR无独立热度贡献；row/column/局部性与Bank同时变化，等待下降不一定省周期。实际安装/迁移/维护/净收益未验证。第一阶段报告中的“未启动第二阶段”仅限该验收步骤范围，不能覆盖随后独立授权的第二阶段。

### 4.3 第二阶段：原合成停止与自然V2分别记录

2026-10-24完成[第二阶段自然完整块V2](page_management_stage2_natural_v2/REPORT.md)：98次新原生、8个已见开发case、140主布局行；旧合成失败不再门控自然。相对冻结起点Q3页级候选0增量，Q15 CA加权−0.003155%；相对加强描述符包络分别−0.000951%/−0.003407%，未达1%工程门槛，NO_PROMOTION。44紧凑布局完整frame重建、6份逐事件身份/重复及原始载荷本地核验通过；row12同址复用/4固定池精确容量不可行。新来源未准入，安装净收益未认证；未改变旧默认或把结论推广为一般页空间无效。


来源：[原S0停止](page_management_stage2_execution_v1/REPORT.md)、[自然V2方案](page_management_stage2_natural_v2/README.md)、[授权修订](page_management_stage2_natural_v2/AUTHORIZATION_AMENDMENT.json)、[最终机器状态](page_management_stage2_natural_v2/FINAL_STATUS.json)、[独立汇总](page_management_stage2_natural_v2/INDEPENDENT_SUMMARY.json)、[新来源门槛](page_management_stage2_natural_v2/INDEPENDENT_BRANCH_GATE.json)。

- 原固定C1在16Bank下，4KiB每张量相位已经达到9槽解析下界，触发STOP_S0_FIXED_C1_NO_STRICT_EXPRESSIVITY_GAP；该轮新原生0、步骤3—5未执行。只否定该解析正例的严格表达力差，非DRAM无收益/自然无空间/所有页配置无效。
- 用户纠正后自然V2不再由合成C1门控；固定Q3层0/24、Q15层0/12，N_DEV/N_TEST共8已见开发case。最初上传自动审批拒绝保留，后用户明确批准目的地，授权修订已解除阻断；不能继续写“等待上传批准”。
- 原1worker执行后有独立调度修订，最多4worker，串行边界与4身份重放保持，总164/12小时上限不变。本地FINAL_STATUS/FINAL_INTEGRITY记录98原生、8case、140主布局行完成，另12同址row对照，独立算术复算已保存；REPORT在24日维护期间由另一聊天补齐，结论NO_PROMOTION。旧STATUS的RUNNING/0原生/一worker仍为早期快照。elapsed_seconds只含90次主矩阵，未含后8哈希/交付时间，不能当98次总耗时；此前“仍在回传”是24日早期状态；25日本地完整验包已通过，见DELIVERY_COMPLETE.json。
- D_star在DEV原生后、TEST参考前冻结：Q3=PHASE4，Q15=XOR4；后增BLOCKHASH4强化包络有单独先冻结证明。Heat/CA采用同源结构代理、预算与3seed；TEST也是旧数据，只是本轮候选先冻后评，不恢复新来源独立性。严格Bank/row对照有不可行/退化项，ROW归因为NOT_IDENTIFIABLE。
- 本地INDEPENDENT_BRANCH_GATE为eligible=false，两模型通过布局列表均空；新独立采集0，general_page_space_claim=UNRESOLVED，NET_UNVERIFIED。这是本有限候选/预算开发门槛未过，不证明所有页布局无效。主机并行时间、状态字节下界或映射构造时长不能当部署净收益。

| N_TEST开发留出比较 | 对D_star周期收益 | 对强化固定包络周期收益 |
|---|---:|---:|
| Q3 HEAT4/CA4 | 0/0 | 0/0 |
| Q3 CA16 | +0.000675% | +0.000675% |
| Q15 HEAT4 | 0 | −0.000024% |
| Q15 CA4 | −0.005411% | −0.005436% |

以上只作独立汇总的有限数值例证，不能挑微小正值代替模型门槛。16/64KiB与全部随机/seed/不可行项保留原完整表；不从几行推全空间最优。25日交付回执确认7.45GB原始归档已完整回本地并验包；24日转运状态保留在历史快照，本维护未运行收尾脚本。

### 4.4 全MoE原式、修订与V4研究冻结

来源：[288完整矩阵](selector_all_moe_formula_v1/FINAL_FORMULA_REPORT.md)、[V2](selector_all_moe_formula_revision_v2/REPORT.md)、[V3](selector_all_moe_formula_revision_v3/REPORT.md)、[V4](selector_exposed_conflict_formula_v4/REPORT.md)、[24文件冻结清单](selector_exposed_conflict_formula_v4/frozen_v1/FREEZE.json)。

- 22日矩阵Q3 192/Q15 96已完整，不再采用16:15的2/192、51/96作当前进度。全部288选RR、相对RR收益0，仍有固定候选oracle后悔；区间漏覆盖未通过，矩阵完成非预测/净收益通过。是独立层块回放求和，不是全模型端到端。
- 后续V2—V4只复用294完整块（288+old/A/B六块）与78人工barrier配置，是开发复核，无新仿真/独立新来源。人工重复的完整块与人工barrier是不同合同，不混合成自然全模型证明。
- V3点选84次CA后，Q3/Q15总周期分别增加0.044017%/0.048707%，最差case退化5.924257%/2.797506%，NO_PROMOTION。V4改用所有候选共享C0和非负暴露惩罚，不把解释更直观当精度提升认证。
- V4：C_hat=C0+tau_fit*rho*Z，Z为128B等效静态服务槽，不是物理事务或真实同时访问；tau_fit约4.632299周期/槽为人工标定，rho为合同/模型拟合倍率，不是测得关键路径暴露比例。此tau_fit不是旧时序预测器17ns参数，旧参数与版本未改。
- 完整294块仍全RR、无RR增量；人工整实验留出38CA/10Heat，Q3/Q15周期收益13.4764%/32.0331%、本批oracle，但不能外推自然块。完整块绝对MARE约9.90%—18.00%、最大54.89%，未认证通用延迟/区间/部署。
- 冻结状态FROZEN_RESEARCH_ONLY_NO_PROMOTION：24个受保护文件、相对路径哈希、参数、评分与数学定义/块级Schedule齐备；只选择布局，不调度原op或DRAM命令，合法性依上游证明，不是已集成端到端交接器。改动另建版本，不能运行校准main或往冻结目录写产物。本次仅重验本地内容哈希。

### 4.5 Challenge3：Q1—Q3已完成，热压力不是策略收益

2026-10-25补齐[Q1—Q3完整本地归档](outputs/qwen_q1_q3_full_archive_20261024_v1/LOCAL_SAVE_REPORT_20261025.md)：主包15735成员、P1参考依赖1470成员和本地补充198项逐项核验通过，含对应运行镜像。UPLOAD_TO_BAIDU目录20文件、5351897685字节，外层SHA256及上传清单覆盖复核通过；未上传网盘，由用户自行上传。此前接收进程中断/TRANSFERRING状态不算完成，本轮补齐后实际验包退出0。旧4.27GB包仍只对应旧批；后文23/24日的“结果证据包/大文件远端”是当时交付范围，完整归档不新增仿真或策略收益证据。

来源：[23日Q1—Q3最终结果](outputs/qwen_hotter_execution_20261022_v3/RESULTS_20261023.md)。三组各256请求、8并发槽位、32代，退出0无OOM；Q4不在该批正式范围。不是32并发。

| 组/输入 | 峰温°C | ≥78°C间歇累计秒 | 最长连续秒 |
|---|---:|---:|---:|
| Q1/768 | 79.202837 | 130.568 | 5.489 |
| Q2/816 | 79.293028 | 148.069 | 4.694 |
| Q3/824 | 79.074963 | 118.360 | 3.395 |

全组≥80/82/85°C时间0，未达82°C目标；累计高温非连续130—148秒，输入更长不保证更热。计算活动约5.9%—6.0%、DMA约51.8%—52.6%，是任务profile平均活动，分区预留不等于持续计算。本次沿报告的保存任务MAC/DAG/资源/生命周期、热轨迹/冻结hash限定复核，不宣称全部KV物理地址、全flows或数值forward已新审计；未重算全256共同窗口95%门槛。

本批未重新筛查合法冷目标，更未运行实际热策略/复制队列/收益对照。此前[P1/P2/P3批](outputs/qwen_hotter_execution_20261021_v2/RESULTS_20261022.md)P1/P2的7471/94独立单步准入、P3无源热up/gate机会只属于那一批，不继承到Q1—Q3。越78不自动产生合法且有收益的动作。

两批既有四组256、CONTROL60 OOM→独立存储修复、偏斜V1→V2及历史未78结果继续按批次保留。[本地约4.27GB完整包](outputs/qwen_hotter_full_archive_20261022_v1/README.txt)仅针对I8/P1/P2/P3，不是Q1—Q3全部原始数据已同包归档；Q1—Q3在23/24日仅结果证据包的交付范围已由25日完整本地归档补齐；不是装入旧4.27GB包。所有热结果为32GiB归档架构、MODELED路由、有限Baseline，不是4/8GiB规范架构、稳态、硬governor或AMBER/Ours收益。

### 4.6 其他历史结论与当前写作边界

- [Q3目标FP16参考](selector_all_moe_formula_v1/TARGET_FP16_REPORT.md)384/384在原容差内通过但源BF16仍141/384输出失败；数值实现、模型保真、周期和工程收益不互相改判。
- [历史单块选择器](selector_real_holdout_v1/REPORT.md)A/B已用、后悔0而RR也过门槛，规划约60—150秒非低成本；[轻量V3](selector_lightweight_delta_revision_v3/REPORT.md)字节正确/API1.504695秒超1秒、步骤6—7未执行。新V4研究冻结不修复旧部署成本失败。
- [旧WHISPER](whisper_coaccess_v1/FINAL_REPORT.md)CA/RR同周期、[旧Q15 memory-stress](COACCESS_BANK_LAYOUT_QWEN3_QWEN15_REPORT.md)对original约3.49%/单随机约0.250%、早期round12迁移失败与起点修正等均按旧合同保留。第一阶段自然O新结论不重写旧负载结论，也不等于胜负原Sem-MoE完整系统。
- Challenge1论文撰写聊天正在修改原理解释、命名与Design/Experiment；草稿措辞或用户要求“所有MoE共通”不成为所有MoE实测收益事实。旧soft70 pager-matched单cohort的30.39%不能冒充当前自然对O收益或CA对Heat纯增量；当前论文工作副本已采用Bank-Delay-Aware Page Layout（BDPL），见`challenge1_target_revision_20261024_v3/CHANGE_NOTE.md`；此为稿件命名，不改变V4冻结文件、参数或收益等级。第二阶段在稿中作为补充布局空间实验，不自动成为BDPL选择器性能验证。

## 5. 架构、接口与术语

- V3.5/V3.6图中每partition的4个逻辑投影Bank，与Ramulator2实际16个decoded Bank是不同层次；NPU SRAM Bank又是另一对象。
- 每个CH/partition整体与对应NPU一对一通过HB接口连接。不能把4个逻辑Bank画成4条独立接口后把总带宽乘4。
- V3.6是V3.5的容量分叉：总容量4→8 GiB，每partition256→512 MiB，地址partition selector `[31:28]`→`[32:29]`；不意味着带宽、Bank数或NPU数量翻倍。依据为两版README及各自冻结配置。
- V3.6规范配置与部分耦合二进制存在事务/位宽ABI冲突；Qwen1.5 smoke使用execution overlay恢复接口字段。必须注明overlay路径、二进制哈希和proxy性质，不修改规范配置来掩盖差异。见 `qwen1_5_moe_a2_7b_v3_6/README.md`。
- 本工作区4 GiB V3.5绝对热执行仍受HB几何、层厚和interface RC等缺项限制；Challenge3归档32 GiB架构已有热运行，不能作为前者HB物理热验证。HB带宽、固定传播延迟、DRAM tCK和事务服务floor不得互换。
- HiBand项目参考模型、论文8×8 split-Benes实现、H2-LLM参数来源、HBSpec架构不是同一对象。
- Qwen3逻辑专家单元、Qwen1.5 sampled 4KiB页和后来完整页事务的粒度不同；不能直接比较“改动页数”或套用同一边定义。

## 6. CoAccess建模与实验规则

1. 先明确已知输入、决策变量、目标/约束；区分项目提出的形式化与论文原本求解的模型。不能把多个独立机制包装成论文不存在的联合优化器。
2. 明确节点是专家、张量块还是物理页，边是波次共现、操作区间交叠、submit窗口还是实际服务等待；写清时间单位和backpressure依赖。
3. 频率不等于同时访问，跨用户同Bank等待不等于全部控制器队列等待。同一物理页冲突不能靠把该页整体换Bank消除；复制、条带化、调度需要另外计成本。
4. 默认固定expert→partition归属，只改partition内Bank布局；跨partition改动必须计NoC、迁移和容量代价。
5. 画像与留出请求互斥；冻结方法、窗口、seed、代码哈希、请求划分与升级门槛。研究过的留出集若用于改方法，应改称开发集并另取新数据。
6. 对照至少覆盖original、round-robin、heat、coaccess和适当随机布局；需要隔离信息增量时，heat/coaccess使用相同冷页规则、候选集合、容量/热度约束和配对seed，不挑最优seed。
7. 分别报告覆盖率、代理指标、容量/改动页数、周期及归因；oracle只能作不可部署上界。采样与represented_bytes、量化元数据、驻留集和activation workspace要显式核算。
8. 完成事件必须真正阻塞消费者；不将离线计算/DRAM/NoC开销简单相加冒充耦合仿真。敏感性无变化时先排查固定floor、采样或依赖路径。

## 7. 运行与维护

- 本地为Windows PowerShell，远端实验记录多用`myserver-113`。远端路径、运行状态和授权按当前任务重新核对；本次2026-10-26文档维护没有连接远端、停止进程或修改自动化。
- 先阅读脚本再运行，尤其`build_*`、materializer、GitHub fork/PR脚本、远端runner和批量仿真脚本；不要因为README有命令就自动执行。
- V3.5入口与验证脚本见其README：`run_whisper_v3_5.py`、`validate_whisper_v3_5.py`、`validate_v3_5_workcopy.py`。使用时先核对该脚本参数和冻结manifest。
- DeepStack AE的`setup.sh`/`run.sh`面向Linux/Conda，不能在PowerShell直接假定可用；完整复现有独立资源需求。
- 新实验保存协议、输入/模型/二进制哈希、命令、日志、manifest、验收结果、失败记录及数据/图表来源。协议修订写amendment，不静默改原文件。
- 不自动清理`tmp`、`_tmp_*`、render/QA目录、归档包或重复文件；名称不能证明其可删。先确认生成来源和是否为唯一证据。
- 修改文档只做路径、数值来源和内容一致性检查；修改模拟器/分配器时运行对应范围的守恒、地址解码、事务完整性、依赖及回归验证。
- 更新研究结论时同步目标目录状态、全项目事实基线和对话索引；新增历史明细写入研究记录并链接，不在本指南末尾反复堆叠整段流水账；保留历史结论的日期、适用范围及被后续验证限制的原因。

## 8. 维护覆盖与历史导航

本地清单只计可读元数据，排除Git、依赖/虚拟环境、链接目标及维护输出目录，不展开归档计数，不重新审计所有模型/Trace/远端大日志。扫描与其他聊天并行，非原子备份。

原37条关联聊天及历史注释保留，新增发现3条为40；本轮8聊天全分页118轮含旧轮，单项6500字符/附件非全量；其余保留原日期；非账号全量，本维护聊天另列。最近50未归档枚举限制不变，完整标题与ID见机器索引。

入口：[资产总览](project_maintenance/ASSETS.md)、[对话汇总](project_maintenance/CONVERSATIONS.md)、[26日报告/状态索引](project_maintenance/REPORT_INDEX_20261026.md)、[审查](project_maintenance/REVIEW_20261026.md)。更新前7文件及旧快照完整保存于`project_maintenance/history/before_20261026_update/`；20—24日历史仍保留。历史失败、授权与状态不能脱离时间/目录当成当前新指令。


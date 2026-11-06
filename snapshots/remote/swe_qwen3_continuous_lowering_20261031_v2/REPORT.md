# 完整两层CPU转换、FP32 lowering与SRAM Bank接入

2026-10-31。当前RUNNING，未认定完整层或1—7步完成。真实统一入口于10:44:53（Asia/Shanghai，113运行日志）启动SSE续版。原BF16、host128 GiB＋HB8 GiB、16 NPU/16×512 MiB HB、CPU2.5 GHz、NPU/NoC1 GHz及DRAM1.25 ns换算不改；无新GPU、SWE/agent或隐藏测试调用。

## 本次实际接入

全部759次矩阵、32种M/N/K形状已经接到新的统一执行接口，验收仍待当前运行完成。单token保留64路累加/二分归约与16/标量尾部；batch按原CPU源的K分块和奇数后偶数顺序累加。执行器实际从4 MiB SRAM数组取FP32操作数，经16-lane乘/加/归约事件及Bank服务门控完成，输出经真实HB返回。没有按FP16阵列吞吐给BF16计时。

CPU BF16展开/RNE、RMSNorm、softmax、SiLU、Top8、路由归一化、dispatch metadata、gather/index_add、strided layout、KV追加/位置校验、repeat KV、rotate-half、attention缩放和causal mask已经接入Sniper ROI里的C软件服务。原模型/activation持久语义仍是BF16，FP32只用于无损展开和原FP32累加/softmax等边界。

原BF16参数由Sniper CPU从原checkpoint后备读取；远端专家同时接收原BF16字节和CPU实际展开的FP32临时字节，并核对两者的全位关系后执行。root也通过CPU服务展开真实输入/参数。临时HB区域固定为weight256 MiB、input320 MiB、output324 MiB，tensor不可变区域硬限240 MiB，越界即停。SRAM tile覆盖前核对last-reader，输出commit后才返回。

KV由CPU实际拼接；19→20位置序列由CPU校验。广播/转置等视图通过真实CPU按索引搬移，attention多head结果通过CPU服务汇集。节点记录父节点、reader、CPU服务完成与计算job控制边界；当前仍采用串行、不可变保留的保守基线，不代表动态释放或异步调度验证。

## CPU数学兼容与容量

原softmax的SLEEF16指数依赖AVX-512，未直接在Gainestown目标CPU上执行。已完整枚举2^32个FP32位模式生成16 GiB通用指数数据，并生成全部65536个BF16输入的128 KiB SiLU数据。这是模型无关的软件兼容数据，不是模型新增权重、量化或单输出修补。实际查表进入Sniper访存成本。

指数表SHA256：681720506278ae2d329d66097a7fbf060d0caeae7711881b66fa3d8c84304af6；SiLU表SHA256：7654cac2f44860273acdf664dc20ebe87f5962f432de29755e3b4b596940877b。131072项混合lane指数复查通过；数学参考仍共享原SLEEF依赖，非独立指数算法认证。完整16 GiB表留113，审查包只带完整SHA/构建来源。

61,066,575,648 B原权重＋17,180,000,256 B兼容数据＋536,870,912 B目标CPU暂存预留，小于128 GiB；HB8 GiB独立计。源码中实际mmap与尺寸检查绑定该预算，原host8 GiB规范未改。

CPU主程序以O3、march=nehalem、noAVX/noFMA且无fast-math/FP contraction构建。编译器报告确认BF16转换循环使用128位向量；ELF反汇编未发现AVX指令或YMM/ZMM寄存器。Sniper进程请求禁用glibc的AVX/AVX2/AVX512/FMA分派；静态主程序检查不等于已逐条认证所有动态库。CLFLUSH/MFENCE请求存在，但Sniper缓存维护语义/成本尚未完整认证，不作完整目标时序PASS。

## 已通过的前置检验

72组M1/M2/M19、N1/17/64/65、K19/20/128/768/2048/4096边界检验，19404个FP32结果对未改C源完全一致。该检验使用同一生产SRAM/numeric头文件和内存测试传输，不计原生时序或完整32种负载形状通过。

两层prefill/decode的原CPU路由softmax、Top8槽位、归一化均严格一致；BF16全位型decode/SiLU各65536项、K128/2048 norm，以及gather、index_add、rotate、KV拼接、repeat、mask、缩放、位置校验通过。CPU八路归一化的树形求和首次失败保留；修正为通用顺序求和后，四个原参考和1/2/19/10000批量随机检查通过，没有容差放宽。

6项CPU拒绝控制通过：decode长度错误、softmax NaN、KV错位、gather越界、重复index_add及未知服务。原M1/M6子链的Bank冲突/越界控制及其失败记录继续保留。

另用未改CPU C GEMM重建了完整两层759次原始矩阵参考，共1626944个FP32输出、56阶段文件；这是CPU-only参考，不是目标执行。额外后台审计等待目标结果，按执行顺序比对每次原始FP32输出SHA与56阶段，任何首差都会保留并停止本实验，不以BF16舍入掩盖差异。

## 当前运行与归档

标量初轮在10:28:47开始，执行到Q/K/V、attention、O及router矩阵后，为合法SSE CPU实现修订主动停止。原目录../swe_qwen3_continuous_lowering_20261031_v1的STOP_AMENDMENT/RUN_EXIT、源码和日志保留；它没有完整层通过结论，也不是数值失败。

SSE续版在独立目录运行，12小时上限、任一子进程失败即停；原始独立收尾器、额外759次FP32审计及安全完整归档器均在113后台，不依赖本地会话。最终必须同时核对DELIVERY_STATUS.json、RAW_ORACLE_AUDIT.json及SAFE_DELIVERY_STATUS.json；没有这些最终回执就不能称通过。安全归档会物化共享只读链接并保留全部clock CSV，避免compact阈值漏掉大时钟文件。

117项冻结实现/前置检验/CPU oracle审查快照1541282 B，SHA256为93957ed7eafff4db1c5e831d94ae1847e2698c6575f284e801e647757fef44d4，[本地成员复核](LOCAL_CHECKPOINT_AUDIT.json)通过。它明确为RUNNING审查快照，非目标输出/完成门控验收。冻结源码见checkpoint_review同名子目录。

## 剩余出口与保留范围

等待真实prefill与cached decode两层完成，逐项核对759个FP32输出、56阶段/12严格输出KV、last-reader/临时区覆盖、两轮NoC反馈及全部子进程退出。仍需审查LAYOUT_GAPS，补齐尚未计入的控制、缓存维护和动态释放范围；unknown不得写成零。SRAM32 B条带/每Bank单共享读写端口是显式研究点，原规范未定义其端口/映射；LPDDR5仍为研究服务代理，HB固定电气延迟未知。

另已只读核对工作区NPUSim/npusim_chiplet_memory.cpp：诊断字段`npu_dma_cycles`在当前直接load/store路径实际写入`checkedTransportSize(bytes)`，不能将它当周期相加。本轮使用runtime chipCycle/真实外部completion门控；原始日志与实现保留，不据该误标字段推断1 B/cycle带宽。

保留对原GPU的GEMM、softmax FP32及prefill4249输出/10路由槽位差异，不重称GPU一致、物理性能或HiBand/Sem-MoE收益通过。完整模型和策略实验在本有限两层出口之外。

来源：原七步REPLAN.md；本目录冻结PROTOCOL/FREEZE/WORKER_FREEZE、CPU_PREFLIGHT、MATRIX_PREFLIGHT、CPU_CONTROLS_ISA、MATH_STATUS、CPU_VECTORIZATION、RUN日志、SUPPLEMENTAL_STRICT_GATE及审查快照。最终结果以113同名目录的独立回执为准。

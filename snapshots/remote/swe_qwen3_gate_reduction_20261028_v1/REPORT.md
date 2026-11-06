# swe_qwen3：gate归约定位、单token修复与up接入

日期：2026-10-28。本片段状态PASS_LIMITED_M1_GATE_THEN_UP_SOURCE_TREE；步骤3整体仍PARTIAL。

已修复当前专家49、row0/slot0、M=1路径的gate差异，并在gate通过后接入完整up投影。两投影各768个BF16输出与同一CPU原内核逐位一致。未宣称批量GEMM、原GPU专家中间值、完整专家或完整MoE通过。

## 原因定位与通用修复

旧实现将所有K按单一FP32累加器顺序相加，原CPU BF16 GEMV使用多lane累加及固定归约树。BF16检查点和codec未改变；差异来自实际算术归约合同，而不是给一个输出增加修正值。

先对既有R0002的prefill/decode非空专家调用及额外20行专家49控制输入检查：86组、180行调用、138240个输出。顺序累加对原batch调用有41处差异；通用Kahan候选仍有19处，故不准入。FP64仅作诊断，没有用作目标运算或新精度模型。见[cpu_attempt1](cpu_attempt1/RESULTS.json)、[diagnostic_attempt1](diagnostic_attempt1/RESULTS.json)。

源码定位依据为固定[PyTorch 2.6 GEMV实现](https://github.com/pytorch/pytorch/blob/v2.6.0/aten/src/ATen/native/cpu/ReducedPrecisionFloatGemvFastPathKernel.cpp)和[SIMD归约实现](https://github.com/pytorch/pytorch/blob/v2.6.0/aten/src/ATen/cpu/vec/functional_base.h)。源实现使用多寄存器独立FP32累加及半树合并，SIMD宽度影响具体K顺序。初始按CPU总体AVX512能力采用128lane，仍有7处M1差异，失败保留。[实际注册核查](DISPATCH_INSPECTION.json)读取安装二进制符号和函数指针，确认BF16 GEMV的AVX512注册为空、AVX2非空；CPU总体能力不能代替算子实际分派。

最终采用该安装版AVX2 GEMV对应的通用规则：64个FP32 lane，K按模64分配累加，随后按32/16/8/4/2/1的半树归约，最后原BF16 RNE。规则没有expert ID、token ID或输出序号分支，不查询参考输出作补偿。当前K=2048；不外推尾部尺寸、NaN/Inf/下溢或其他ISA。真实BF16乘积在本次有限数值范围内由FP32乘法表示，未采用FP16/W4或FP64目标运算。

## 必须保留的单token与batch边界

64lane规则对180次独立M1原CPU调用全部逐位一致，gate共138240项0差异；同一规则对up亦为138240项0差异。[gate检查](tree_cpu_attempt2/RESULTS.json)、[up检查](up_cpu_attempt1/RESULTS.json)分别冻结执行。

但是，把这些单token结果拼成batch再对照原CPU batch线性层，两投影各仍有21处差异。较大batch使用不同内核，不能把本次修复称为通用BF16 GEMM一致，也不能把原batch参考改成单token参考后宣称原合同通过。此次可推进的合同仅是上一原生片段本来就固定的M=1专家49算子。所有batch候选失败和差异原样保留，完整prefill专家批量计算仍未准入。

CPU结果JSON继承的up='NOT_RUN'字段表示该CPU检查没有运行目标up；up_cpu_attempt1实际测试投影由冻结cpu_up_tree.py中的up_proj键确定，目标up结果另见native_attempt1，避免将该遗留字段混作未执行CPU检查。

## 目标gate→up与生命周期

沿用原BF16、128 GiB host＋8 GiB HB研究overlay、原规范host8不改。复用真实收件和专家49原safetensors权重，重新绑定选定只读后备及HB区间；不是跨进程保持原模拟器状态。旧权重失败目录和旧执行器不改。

native_attempt1先核验全部M1 gate开发比较及up开发比较均无差异，再执行gate；gate原生BF16结果与CPU逐位通过后，才允许up权重D2H解码、FP32临时展开H2D及up计算。两者均完整遍历2048→768，执行显式FP32向量乘加与源顺序树，无隐藏FP16矩阵调用。

每个SRAM tile的64个算术读取者完成前不允许释放；每投影12个输出tile完成前不允许展开工作区退休。共享输入及原inbox保守保留到gate/up两者完成；物理inbox仍保留，gate/up结果各3072 B FP32影子及HB区间保留给SiLU/乘法等下游，尚未宣称这些消费者已经执行。down原BF16权重继续驻留待用，未运行down。

原生gate完成9848142 ns，up开始12159505 ns、完成13660642 ns；这些是有缺项的显式代理时间，不能用于完整BF16性能或收益结论。up开始严格晚于gate通过。11项门控负对照通过。见[状态](native_attempt1/STATUS.json)、[HB读取者](native_attempt1/HB_LAST_READERS.json)、[算术读取者](native_attempt1/ARITHMETIC_LAST_READERS.json)、[驻留](native_attempt1/RESIDENCY.json)。

## 独立核查与资源

[远端独立审计](native_attempt1/INDEPENDENT_AUDIT.json)重算选定真实权重/分片SHA，以NumPy独立重建64lane FP32树及整数BF16 RNE，gate/up的FP32字节、BF16字节和CPU参考均一致；同时核对原生执行库身份。并重新检查上传commit、依赖事件、DMA窗口、HB读写及SRAM生命周期。本地[因果复核](LOCAL_CAUSALITY_AUDIT.json)只针对回收账本，不声称在Windows重读原远端权重。

原生事件206705、向量op6486528、32 B DRAM事务1284808；HB写22038656 B、读19075200 B。SRAM峰值3145728 B，父阶段与新分配保守叠加HB22861248 B，单CH地址范围50334720 B，未超CH512 MiB/总HB8 GiB；全模型host后备61064245248 B加17 GiB运行/IO预留未超host128 GiB。

host codec/control、gateway及输出D2H/encode时序仍未认证，FP32输出导出是离线数值检查；聚合SRAM服务不等于逐Bank仲裁。未新增NoC或Sniper，没有源GPU gate/up中间量验收。本轮无新GPU、agent、SWE或留出访问，softmax FP32最大1.4901161193847656e-7差异保留。新增原生片段1，本线累计8，Sniper累计3，物理NPU0。

冻结代码/协议和所有CPU失败候选随证据交付，最终成员数及SHA以[DELIVERY](DELIVERY.json)、[本地验包](LOCAL_DELIVERY_VERIFICATION.json)为准。

## 后续

单token分支可接SiLU(gate)×up、down及结果返回，并补中间量last-reader和源专家顺序commit。批量分支另需按实际源batch内核建立合同及验证，21处差异不能忽略。步骤3整体仍PARTIAL，不以SWE修复成功率作为推进门槛。

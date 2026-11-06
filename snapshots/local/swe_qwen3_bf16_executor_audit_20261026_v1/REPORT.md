# swe_qwen3目标执行器BF16语义核查

日期：2026-10-26。结论：**PARTIAL_BF16_CODEC_SOURCE_SEMANTICS_NOT_READY**。

不能直接把现有目标执行器配置成“两字节/BF16”，就认定它支持原Qwen3的BF16推理语义。已有BF16 host codec和部分功能参考能力，不是从零开始；但已查Qwen耦合器只做计算时序，通用NPUSim功能执行的混合精度边界与算子覆盖不足，原生BF16阵列与时序也未认证。

## 1. 核查对象及执行范围

1. 规范`../whisper_operator_inventory/target_architecture_v3_6/npusim_cluster_v3_6.json`、target_architecture_v3_6.yaml。仅声明INT8_ACC_INT32、FP16_ACC_FP32，未列BF16阵列或BF16吞吐；supported_datatypes的文本也不是数值单元实现证明。
2. 旧Qwen3耦合源码`../qwen3_30b_a3b_v3_6_experiment/coupled_main.cc`，与本次113下载的REMOTE_QWEN_COUPLED.cc哈希一致。检查其COMPUTE字段和事件完成逻辑，不执行旧二进制。
3. 交付NPUSim的`../olmoearth_v3_6_integration_20261025_v1/source/NPUSim/npusim_runtime.cpp`、npusim_runtime.h、npusim_tensor_codec.h、onnx_official_parser.cpp。前三文件与当前113指定路径SHA逐项匹配，见REMOTE_IDENTITY.json；parser本轮仅查本地副本。
4. 对照已固定Transformers v4.51.3 Qwen3源码`../mini_swe_operator_graph_v3_6_20261026_v1/source/modeling_qwen3_moe.py`。这是本线结构参考，尚未完成实际GPU后端版本与kernel行为冻结，不能宣称与最终GPU逐位等价。

本轮先只读核查，再在113新隔离目录编译并运行微型CPU源码探针。未加载Qwen权重、未使用GPU、未运行NPUSim时序/PopNet/Ramulator、未修改原执行器/配置，没有完整模型或benchmark推理。

新目录：/mnt/sda1/h3240101068/swe_qwen3_bf16_executor_audit_20261026_v1。探针包含原runtime.cpp来调用内部功能函数，用既有nlohmann头、g++11.4、-O0/-fno-fast-math/-ffp-contract=off与gc-sections编译；不是原已部署二进制的行为认证。完整命令、输出与hash在PROBE_RECEIPT_V2.json。

## 2. 分层结果

| 层次 | 结果 | 支持范围 |
|---|---|---|
| BF16编码/解码/两字节payload | PASS_LIMITED_CPU_CODEC | kBf16、显式字符串/线协议、RNE转换存在，有限位型往返与选定tie检查通过 |
| BF16输入/权重＋host FP32功能计算 | PARTIAL_REFERENCE | 可在输入/权重和部分边界舍入；不是原生硬件BF16乘加 |
| 原Qwen3混合精度/舍入边界 | NOT_READY | 全局activation dtype/round_each_operator不足以表达不同op和tensor的BF16/FP32语义 |
| 通用Qwen3算子图覆盖 | INCOMPLETE | 该通用executeNode缺少TopK、Gather、ScatterElements、Cast、Sin、Cos等；可另lowering但尚未实现/验收 |
| 旧Qwen3耦合COMPUTE | TIMING_ONLY | 读取cycles和资源份额排完成事件，无张量操作数/结果或dtype求值 |
| BF16目标MAC/向量真实时序 | UNVERIFIED | 通用event scheduler按ops与配置吞吐计时，没有BF16专用服务能力证明 |
| 完整BF16模型/任务等价 | NOT_RUN | 本轮没有模型、完整Block0、GPU参照或SWE任务验收 |

## 3. 已有的BF16能力

npusim_tensor_codec.h定义kFp32=1/kFp16=2/kBf16=3，BF16两字节little-endian payload；floatToBf16Bits采用round-to-nearest-even，保留NaN类别；bf16BitsToFloat将位型拓宽到host float。onnx_official_parser.cpp也包含BFLOAT16 initializer读取分支。

CPU探针对65,280种有限BF16位型检查encode/decode往返，零不匹配；两项指定FP32→BF16 halfway tie通过；3元素payload为6 B。1e10在BF16往返后保持有限、转FP16溢出，说明“都是两字节”不能互换格式。该检查不覆盖所有FP32舍入输入、所有NaN载荷或GPU FTZ/NaN策略，不构成整体BF16运算认证。

源码loadConfig按字节数回退：4 B默认FP32，2 B默认FP16。必须显式设置activation_dtype、weight_dtype、output_dtype为bf16、accumulator_dtype为fp32才能选择BF16边界。规范副本当前没有这些显式字段，不能只改字节或依赖注释。此处是配置选择能力，不是建议直接把全局BF16当最终Qwen适配。

## 4. 为什么全局BF16设置仍不够

### 4.1 Router softmax必须保留FP32到Top8和归一化后

源Qwen3执行F.softmax(router_logits,dtype=torch.float)，在FP32概率上做Top8与归一化，然后才转换到hidden dtype。

通用executeOnnxFunctionally在round_each_operator开启时，把每个非整数节点输出统一转activation_dtype；所以activation_dtype=BF16会把Softmax结果提前舍入。即使最终output_dtype=FP32也不能恢复丢失的中间精度。

实际源码CPU探针，输入[1,2,3]（均可精确表示为BF16）：

- FP32 Softmax：[0.0900305733, 0.2447284758, 0.6652409434]；
- 全局BF16边界、最终FP32输出：[0.08984375, 0.2451171875, 0.6640625]。

这证明当前全局舍入边界不同，不是完整Qwen路由错误率统计。关闭round_each_operator又会漏掉源模型应有的BF16回写，不能作为通用修复。

### 4.2 RMSNorm的cast位置不同

源Qwen3：BF16输入→FP32平方/均值/rsqrt→归一化→转回BF16→乘BF16 learned scale。通用rmsNormalization则在FP32完成归一化与scale相乘，随后由外层一次舍入。

探针刻意让两边使用相同的标量FP32 inverse_rms，只隔离“scale前还是后cast”。128×8=1024个确定性BF16元素中258个结果不同；首例源式两次舍入-0.3125、通用fused后一次舍入-0.310546875。这是构造反例，不是任务分布、容差失败率或真实GPU错误率。原始输入/weight见CPU_PROBE_RESULT.json。

### 4.3 其他混合精度和算子缺口

源RoPE频率/三角函数显式用FP32后回写；通用函数把全部非整数initializers统一转weight dtype，也可能错误改变本应FP32保留的常量。attention softmax、专家加权/index_add顺序、残差和不同边界均需逐tensor/op合同。

本次对通用executeNode实际探测TopK、Gather、ScatterElements、Cast、Sin、Cos，均返回unsupported ONNX op，与源码dispatch列表一致。不能据此推断所有项目lowering都不可能实现这些op；结论只限这条已查通用路径。但完整Qwen3不能直接交给该路径执行。

MatMul功能函数用host float顺序K循环，每次累加后可按accumulator_dtype转换；这不是源GPU张量核归约树、融合行为或特殊值处理的位级证明。单凭BF16输入/FP32累加名称相同不够。

## 5. 计算时序与数值必须分开

旧Qwen耦合Op含kind/bytes/address/cycles/phase/scope等，没有实际计算tensor。COMPUTE直接以ceil(cycles/(share*frequency))调度完成；因此它可以接纳由BF16轨迹构建的图，但没有执行BF16数学，不能据此声称BF16数值支持。

NPUSim NpuProgramEvent的MAC/vector/reduce事件同样描述ops/资源/依赖，数值在另一条host功能路径或工作负载适配器求值。通用MAC事件按config.mac_ops_per_cycle计时，不由BF16 dtype自动获得合法吞吐。现有2048 FP16 MAC/cycle不能自动给BF16使用。

已有OLMoEarth/DINO的CPU求值＋原生事件有限验证也不能提升为BF16 Qwen认证；同样不能为了跑通改变BF16为FP16。

## 6. 下一步需要补什么

1. 先给Qwen3逐op/tensor建立BF16/FP32 dtype、舍入和顺序合同，尤其router、RMSNorm、RoPE和expert combine；不要只设置全局activation_dtype。
2. 新建隔离的Qwen3 BF16功能适配器：复用codec，补缺失op/显式cast/混合精度边界，并在真实同源fixture上对GPU BF16逐阶段检查。目标运算合同与GPUkernel细节分别记录，不许直接放宽原门槛。
3. 在当前架构未证明BF16阵列能力前，功能路径可标CPU BF16语义参考；BF16设备时序仍阻断。若选择现有FP32向量原语的软件lowering，必须实现并计数/验证每条原语、存储和转换，不套FP16阵列吞吐；若新增硬件BF16模式则另立架构修订。
4. 通过后才能将BF16功能输出与分页/NoC/内存完成门控结合，先单op/单层，再两层/真实工具片段；host128/HB8固定约束保持不变。

本轮结论不是“BF16完全不支持”，而是“编码和部分参考支持已确认，原Qwen3 BF16语义与目标时序尚不能直接使用”。

## 7. 失败与复核记录

首次CPU探针漏设测试Model的graph input shape，触发`functional ONNX execution lacks shape for graph input x`而退出；这是探针fixture错误，不作为BF16不支持证据。原回执保留PROBE_RECEIPT_ATTEMPT1.json。修订2补齐shape，编译与运行均退出0。原target源码未改；remote旧probe源/二进制与失败现场未清理。

## 8. 来源

- NPUSim源码：../olmoearth_v3_6_integration_20261025_v1/source/NPUSim/npusim_tensor_codec.h:20、184起；npusim_runtime.cpp:708、936、1822、1857、2074起；npusim_runtime.h:115起；onnx_official_parser.cpp:182起。
- 源模型：../mini_swe_operator_graph_v3_6_20261026_v1/source/modeling_qwen3_moe.py:259—287、302—306、435起。
- 目标配置：../whisper_operator_inventory/target_architecture_v3_6/npusim_cluster_v3_6.json:24—31；target_architecture_v3_6.yaml。
- 旧Qwen执行器：REMOTE_QWEN_COUPLED.cc及REMOTE_IDENTITY.json；与../qwen3_30b_a3b_v3_6_experiment/coupled_main.cc哈希一致。
- 本轮实际检查：cpu_source_probe.cpp、PROBE_RECEIPT_V2.json、CPU_PROBE_RESULT.json；source/probe/hash关系见SOURCE_MANIFEST.json。

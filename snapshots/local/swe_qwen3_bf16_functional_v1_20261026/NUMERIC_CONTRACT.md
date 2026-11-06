# 步骤1：Qwen3 BF16逐算子功能合同 v1

## 身份、范围和禁止事项

benchmark为swe_qwen3，host128 GiB/HB8 GiB固定。原始模型BF16 checkpoint revision为ad44e777bcd18fa416d9da3bd8f70d33ebb85d39。结构语义参考固定Transformers v4.51.3的modeling_qwen3_moe.py，源文件SHA为3af43d01f9f902c8009b6dd7d7b8b563561b53dd0aa54175f585ae90d049fdb8。原mini-swe-agent提交04d809ceab9df28f9adaed044884180159172930保持不变。

本阶段实现CPU功能适配器，沿用既有NPUSim BF16 codec；PyTorch CPU提供功能算术，不是FP16模型、GPU kernel、目标NPU指令或时序模拟。真实GPU backend/依赖尚未完成步骤3冻结，本合同不得宣称GPU或完整模型逐位一致。BF16矩阵内核归约/FMA属于所记录CPU backend；不声称已认证为目标FP32累加树。

不使用W4/INT4，不将模型转换FP16，不按2字节猜格式，不把整数shape/index/position舍入BF16，不把全部FP32常量转成BF16权重。不计周期，不调用GPU，不加载checkpoint，不改旧NPUSim。

## 逐算子规则

| 算子/数据 | 输入/存储 | 内部及舍入 | 输出 |
|---|---|---|---|
| BF16 codec | BF16位型/FP32 host值 | 复用npusim_tensor_codec.h的RNE转换；实际payload2 B；NaN类别检查不宣称NaN载荷跨backend一致 | BF16或精确扩展FP32 |
| Linear/MatMul | BF16 input/weight | 当前为记录版本的PyTorch CPU BF16 kernel；不得套目标吞吐或假定内部K归约；BF16 API结果再经codec为幂等边界 | BF16 |
| RMSNorm | BF16 hidden、BF16 learned scale | hidden先FP32；平方/mean/rsqrt/归一化均FP32；归一化先回BF16再乘BF16 scale、回写BF16；epsilon为FP32标量 | BF16；中间variance/rsqrt保留FP32 |
| Router softmax | BF16 logits | softmax(dtype=FP32)，不得早舍入；非有限值沿backend传播 | FP32概率 |
| TopK与renorm | FP32概率 | TopK默认largest/sorted；FP32求和、归一化后才转BF16；tie身份沿已冻结backend，不私设expert-ID tie排序 | int64 IDs、BF16最终weights |
| SiLU/SwiGLU | BF16 gate/up投影 | F.silu的CPU BF16融合语义先输出BF16，再与up逐元素乘并回BF16，down linear输出BF16 | BF16 |
| Expert dispatch/combine | int64 IDs、BF16 token/weights | 专家按升序；每专家slot/token排序与源torch.where一致；输出乘BF16最终权重，按源index_add调用顺序合并 | BF16 |
| Residual/add/mul | BF16 | 独立算子边界回BF16，不擅自融合多算子 | BF16 |
| RoPE tables | int64 position、FP32 inv_freq | 原FP32频率matmul、cos/sin；最后转hidden BF16；默认rope、scaling1，不支持未声明动态rope扩展 | BF16 cos/sin，日志可见FP32中间 |
| Apply RoPE | BF16 Q/K/cos/sin | rotate-half＋各BF16乘法边界＋BF16相加，禁止用一个FP32融合表达式代替 | BF16 |
| Eager GQA | BF16 Q/K/V | repeat KV；QK BF16结果、scale边界、BF16 mask；softmax FP32后回query BF16，AV BF16；eval、dropout0 | BF16 output/probabilities |
| KV | BF16 K/V，int64 cache_position | 独立session/layer、顺序append；不覆盖、不隐式重试，不引入KV量化；静态/paged/sliding cache尚未实现 | BF16 cache |
| Gather | 原tensor dtype、int64 indices | ONNX Gather形状语义，负索引显式规范化；越界拒绝，不将513等整数变512 | 原dtype |
| ScatterElements | 原dtype、int64 indices | 仅add归约通过此合同；重复索引replace顺序不认证、不静默实现 | 原dtype |
| Cast | BF16/FP32 float、int64 metadata | 仅显式BF16↔FP32或int64 identity；禁FP16模型/整数到BF16捷径 | 显式dtype |

## 比较门槛（运行前固定）

1. CPU同backend、同源输入/权重、eval模式：有限数值要求逐元素精确相等；元数据/ID在非平局条件要求精确相等。NaN/Inf比较分类与符号，NaN载荷不认证。测试报告不得用宽松容差掩盖本阶段实现差异。
2. FP32 router与norm中间值必须保持FP32，不能只比较最终BF16输出。回归覆盖既有softmax早舍入、RMSNorm cast-before-scale反例，并增加非特判输入。
3. TopK平局：只保证在当前CPUbackend与原函数同输入相同结果；记录backend返回ID，不推导未来GPU会相同。GPU真实fixture以后重新验收，不能借平局修改判据。
4. 低成本确定性合成输入检查边界、混合精度、整数513、重复index、KV追加和session隔离。完整Qwen几何只做单算子/单专家/单attention子链；小维度MoE仅检验组合，不称原完整层或任务PASS。
5. 数值测试不等于目标时序/物理硬件或CPU/GPU跨backend等价。真实任务fixture、最终GPU版本、完整层/两层、SDPA/FlashAttention、全模型生成均留后续步骤；未完成项必须保留。

## 测试引用与复现

test_adapter.py从固定原始源码AST提取RMSNorm、MLP、SparseMoeBlock、Attention和RoPE相关原方法作为同backend对照，不重写这些原方法。仅为不安装Transformers而提供必要的config/函数注册表、移除方法装饰器并记录范围；原body保持原样，代码与AST节点hash留证。原方法仍调用相同PyTorch CPU后端，因此是源码边界/适配器回归，不是独立低层矩阵内核认证。

实际使用的Python/torch/numpy版本、CPU线程和源码/codec动态库hash以运行回执为准。首次运行前的合同hash需单独保存；如失败，保留原报告与修订，不事后放宽阈值。

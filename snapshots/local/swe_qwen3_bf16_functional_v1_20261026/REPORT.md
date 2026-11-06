# swe_qwen3步骤1—2：逐算子合同与BF16功能适配器

日期：2026-10-26。结论：**PASS_LIMITED_CPU_SYNTHETIC_SOURCE_SEMANTICS**。逐算子合同和隔离CPU功能适配器已交付；本轮51项检查、0失败。不是原checkpoint数值认证、完整层/模型/SWE任务、GPU、目标NPU或BF16时序验收。

## 1. 完成了什么

步骤1：运行前固定NUMERIC_CONTRACT.md与RUN_PROTOCOL.json，逐op明确BF16/FP32、舍入、顺序、特殊值与元数据规则。OP_DTYPE_AND_ROUNDING_CONTRACT.json是对应机器表与实际CPU版本绑定；实际GPUkernel仍留步骤3绑定，未编造成已验证来源。

步骤2：bf16_adapter.py提供独立功能入口，复用既有NPUSim codec的薄封装codec_bridge.cpp，不修改旧NPUSim/旧Qwen耦合器。功能包括：显式cast、linear/matmul、RMSNorm、FP32 softmax与TopK/归一化、gather、additive scatter/index_add、SwiGLU、按源顺序MoE、默认RoPE、eager GQA、按session/layer隔离的追加式KV。

所有算术在CPU上求值，输出使用真实BF16 dtype/codec；不走FP16/W4，不给任何op填写周期。269条FUNCTIONAL_EVENTS仅记录方法、dtype、shape、字节和UNMODELED标志，不是设备事件、硬件事务或已耦合执行DAG。

## 2. 修复此前发现的具体语义缺口

- Router：BF16 logits→FP32 softmax→FP32 TopK与归一化→BF16最终weights，概率中间值不早舍入。
- RMSNorm：FP32平方/均值/rsqrt/归一化，先转BF16再乘BF16 scale，修复通用fused后统一舍入的边界差异。
- RoPE：int64位置与FP32 inv_freq保留，频率、cos/sin用FP32，输出回BF16；旋转的乘/加边界分别保留，不改成单个FP32融合式。
- MoE：保留源expert升序与torch.where给出的slot/token顺序，按源index_add调用序列合并；没有私设expert-ID tie排序。
- 元数据：shape/index/position始终int64，覆盖513不能变成512；不以global activation dtype污染它们。
- KV：按session/layer独立append，拒绝不连续位置/重复追加和几何变化；无静默覆盖、KV量化或滑窗替换。

## 3. 实际验证范围

原始对照是固定Transformers v4.51.3 source中提取的原函数body：RMSNorm、MLP、SparseMoeBlock、Attention、RoPE与helpers。AST节点hash记入RESULTS。为独立于本机旧Transformers安装，仅提供config/注册表、默认RoPE initializer，移除autograd/dynamic-rope装饰器；body不重写。测试是同PyTorch CPU backend源码边界回归，不是独立矩阵内核或GPU逐位等价验证。

| 覆盖 | 实际检查内容 |
|---|---|
| Native codec | 16,392个确定性FP32位型与torch BF16边界比较；65,536个BF16位型decode，有限位型roundtrip；NaN按分类而非payload |
| 旧失败反例 | 原softmax早舍入及RMSNorm cast-before-scale反例均对源函数精确一致 |
| RMSNorm | 8/128/2048维与非单位scale，验证shared head scale和hidden scale |
| Router | H2048/E128/Top8，非平局与构造平局，FP32中间概率及BF16最终权重、ID |
| 单专家 | H2048/I768，3 token，gate/up/SiLU/product/down对源MLP精确一致 |
| RoPE/GQA | Q32/KV4/D128；prefill3 token后两次cached decode；输出与attention probability均精确一致 |
| 元数据/索引 | 513、负/标量gather、越界与错误dtype拒绝、重复index_add/scatter-add |
| KV | cache长度、session/layer隔离、重复位置拒绝，独立source cache做对照 |
| MoE组合 | 小维度H32、16专家、Top8、5 token，输出/route logits与原函数一致，40个assignment守恒；不是完整原层 |
| 范围守卫 | 无FP16功能记录、所有记录CPU/无时序、CUDA未初始化 |

51是检查项数量，不是独立任务/样本数。对源同backend有限值要求精确相等，没有放宽容差。最终BF16权重和允许表示误差预算只作附加检查，不能替代精确源比较。GPU TopK平局、不同kernel归约与特殊值处理仍未知。

来源：attempt1/RESULTS.json、attempt1/FUNCTIONAL_EVENTS.json、test_adapter.py、运行前RUN_PROTOCOL.json。

## 4. 环境与复现

本机Windows的torch导入触发_C DLL加载失败，未安装或修复共享环境；测试改用113既有环境：/mnt/sda1/h3240101068/legosim_four_workloads_step3_20261024_v1/venv/bin/python。实际Python3.11.16、torch2.6.0+cu124、numpy2.4.6、CPU单线程、mkldnn开启、cuda_initialized=false。

远端新目录：/mnt/sda1/h3240101068/swe_qwen3_bf16_functional_v1_20261026。源码、合同与codec header预先核SHA；桥采用g++、-O0、-fno-fast-math、-ffp-contract=off编译。本轮远端首次适配器测试attempt1退出0，未重跑挑结果。ATTEMPT1_RECEIPT.json保存完整编译/运行命令、stdout、无stderr和hash。

依赖原NPUSim codec的SHA为0b281590e1a5e2dc7d416490226e96a8328ebd3af685f89a4837dedae25bec12，模型参考源码SHA为3af43d01f9f902c8009b6dd7d7b8b563561b53dd0aa54175f585ae90d049fdb8。codec动态库hash见回执。源模型权重未读取；所有输入和模块权重是确定性合成测试数据。

重跑需另指定不存在的新输出目录，不覆盖attempt1。命令结构为已记录python运行test_adapter.py，传--source固定源码、--codec桥库、--out新目录；以ATTEMPT1_RECEIPT.json为实际命令来源，不在这里自动执行。

## 5. 尚未完成与下一步

已完成：CPU参考范围的语义合同、codec复用、隔离功能适配器及有限合成op/subchain验收。无训练、完整模型加载、SWE任务或目标时序运行，旧执行器未修改。

仍待后续：实际GPU后端/版本冻结、原checkpoint真实fixture、完整原层/两层/模型、真实prefill/decode路由和工具会话。当前eager/default-RoPE/append-only KV不覆盖SDPA/FlashAttention、dynamic RoPE、paged/static/sliding KV，Scatter replacement顺序也未实现。

目标BF16吞吐、FP32向量软件lowering的设备成本、分页/NoC/存储耦合仍阻断。CPU backend的BF16 linear/matmul不能提升为目标阵列BF16支持，不能套2048 FP16 MAC/cycle。

当前可推进下一步是在资源核查后建立原BF16 GPU功能基准、采真实fixture，再逐阶段核验本适配器。不得据本报告直接进入四方案性能结论。

## 6. 原始来源

- 运行前合同：NUMERIC_CONTRACT.md、RUN_PROTOCOL.json。
- 机器合同/实现：OP_DTYPE_AND_ROUNDING_CONTRACT.json、bf16_adapter.py、codec_bridge.cpp。
- 对照来源：../mini_swe_operator_graph_v3_6_20261026_v1/source/modeling_qwen3_moe.py；原BF16执行器审查见../swe_qwen3_bf16_executor_audit_20261026_v1/REPORT.md。
- codec：../olmoearth_v3_6_integration_20261025_v1/source/NPUSim/npusim_tensor_codec.h。
- 验收：ATTEMPT1_RECEIPT.json、attempt1/RESULTS.json、attempt1/FUNCTIONAL_EVENTS.json；SOURCE_BINDINGS.json与ARTIFACT_MANIFEST.json保存绑定。

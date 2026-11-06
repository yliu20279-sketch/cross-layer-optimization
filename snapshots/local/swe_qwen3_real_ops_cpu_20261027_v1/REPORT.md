# swe_qwen3：真实算子、层0功能与候选映射推进

日期：2026-10-27。状态：PASS_LIMITED_REAL_CPU_SOURCE_LAYER0；跨GPU数值一致性仍未通过，目标事件/时序未运行。本轮沿新分线计划，不等待SWE修复；未启动agent、新GPU采集或读取新留出。

## 实际完成

1. 两个固定既有请求：短生成R0002（19-token prefill与首decode），v6开发R0001（738-token分块prefill与首decode）。原请求成员SHA核查通过，原权重实际按key载入，无FP16/W4替换。
2. 同CPU原源码与适配器138项比较全部逐位一致：真实norm、router、attention/概率、93次专家调用、3段记录dispatch的MoE组合。184总检查包含跨GPU比较和诊断，169精确不能作为成功率。原函数与适配器共享PyTorch CPU数值内核，因此仍非独立低层内核认证。来源：attempt1/RESULTS.json、FUNCTIONAL_EVENTS.json、PRE_RUN_FREEZE.json。
3. 进一步加载原层0全部393个参数张量，623120640元素，在同一CPU对未修改Transformers原DecoderLayer验证完整prefill和cached decode。完整层输出与K/V两阶段均逐位一致；router由CPU自主生成，没有注入记录。cos/sin作为同源层输入使用原fixture值，未在此验证完整模型RoPE生成。来源：layer_attempt1/RESULTS.json、check_full_layer.py、LAYER_PRE_RUN_FREEZE.json。
4. 目标软件候选：原NPUSim codec＋显式BF16→FP32乘/加→BF16软件linear，在短请求router的prefill/decode均与原GPU logits精确一致；仅host功能求值，不是NPUSim设备事件。来源：mapping_attempt1/RESULTS.json、bf16_vector_bridge.cpp。
5. EP16 origin分发/专家返回顺序检查：保留原slot/token及专家升序合并，两阶段对canonical逐位一致。反例按rank排序合并：prefill20251元素不同、最大差0.0078125；decode1144元素不同、最大差0.0009765625。这要求目标映射显式约束commit顺序，不能按到达顺序累加。来源：mapping_attempt1/RESULTS.json、TARGET_MAPPING_CONTRACT.md。

## 差异诊断与未通过边界

RMSNorm：原CPU式仍有16个元素与GPU不符。已定位在开发chunk1的token133；FP64方差回写FP32与原FP32方差相同，单改方差精度不能消除差异；仅用FP64诊断rsqrt后回FP32，16个差异均消失。这说明该rsqrt变体足以解释当前样例输出差异，但没有保存原GPU中间值，不能证明其具体kernel/指令。未修改原适配器或提高模型精度。来源：NORM_DIAGNOSIS.json。

Top8：只从同一捕获logit比较CPU/GPU选择，非平局486行全部ID一致；39行专家集合不同，均落在第8/9名边界平局。内部平局也可改变slot顺序。此检查不包括CPU GEMM扰动后的完整自主router：真实router GEMM对GPU在两块各有2个元素差异、最大0.03125，所以全router不能简单只归因于平局。来源：attempt1/RESULTS.json的topk_diagnostics与router检查。仍未用自定义expert-ID tie-break冒充源GPU行为。

完整层：CPU同源prefill/decode通过；对原GPU，prefill有4249个元素不同、最大0.0068359375，decode恰好逐位一致。两者是有限样例，不能将一个decode的相等外推到整个模型。来源：layer_attempt1/RESULTS.json。

attention：适配器对CPU原函数7/7精确，对原GPU仅1/7精确；RoPE cos有一阶段2元素差异。全部原始差异保留，不事后放宽容差。来源：attempt1/RESULTS.json。

注意：attempt1里名为recorded_dispatch_layer_output_vs_GPU的比较使用捕获attention_output/moe_input和实际dispatch，是条件子链重组，不是自主完整层。真正完整层对照单独在layer_attempt1；不得混称3个完整层GPU验证。

## 来源、交付与下一步

PROVENANCE_VERIFICATION.json重算层0所用1个完整权重分片SHA，并与旧FIXTURE_WEIGHT_BINDINGS逐项一致；config/index及运行前协议/代码冻结也核验一致。没有重算整模型全部61GB，也没有证明旧包外其他文件身份。代码/结果交付清单为DELIVERY_MANIFEST.json，本地逐成员核验另见LOCAL_EVIDENCE_VERIFICATION.json。

原BF16、host128GiB/HB8GiB overlay不变，原目标host8规范不改，NPU运行0。当前是CPU源码语义与候选软件映射进展；完整模型、两层真实GPU参考、目标BF16指令与时序、分页NoC/SRAM生命周期以及Sem-MoE/HiBand收益均未认证。

下一步按TARGET_MAPPING_CONTRACT.md推进有界单op的目标软件原语/完成门控；rsqrt/TopK跨backend差异单独保留，不阻断其他已可验证op。若需要补源GPU中间量，只对已有登记输入一次有界forward采集，不重跑SWE。现有agent后台任务本轮未改动，不作为上述功能工作的门槛。

原来源：../swe_qwen3_step3_reference_replan_20261027_v1/PLAN.md；../swe_qwen3_bf16_functional_v1_20261026/NUMERIC_CONTRACT.md及bf16_adapter.py；../mini_swe_operator_graph_v3_6_20261026_v1/source/modeling_qwen3_moe.py；../whisper_operator_inventory/target_architecture_v3_6/target_architecture_v3_6.yaml。原代码、失败结果及旧证据均保留。

# mini-SWE＋Qwen3：算子拆分、任务图与V3.6映射

日期：2026-10-26（Asia/Shanghai）。状态：STRUCTURAL_DELIVERY_ONLY；无模型加载、任务运行或NPUSim/PopNet/Ramulator执行。本交付先于性能实验规划，取代直接从环境安装进入四方案比较的顺序。

当前后续步骤详见[复现步骤修订2](REPRODUCTION_STEPS_V2.md)，本报告的算子/容量结果不变。

存储后续选择见[旧方案审查及本线配置](../mini_swe_storage_audit_20261026_v1/REPORT.md)：新研究profile为8 GiB HB＋128 GiB host的显式host容量overlay，保留完整BF16只读后备。下文针对原8 GiB host的容量阻断仍成立；新profile的容量预算通过不代表pager/时序/BF16算术通过。

## 交付入口与证据边界

[本地总览](index.html)包含三张SVG/PNG图：[agent任务控制流](01_task_control.svg)、[单个Decoder层](02_decoder_layer.svg)、[V3.6候选映射](03_target_mapping.svg)。算子清单见OPERATOR_INVENTORY.csv；两份48层展开图见prefill_graph.json、decode_graph.json及对应CSV；架构映射见MAPPING.json；容量见CAPACITY.json；重排计划见REPLAN.md。

模型图每个阶段有1595个符号节点、2218条依赖，均通过端点检查、拓扑无环检查与48层完整性检查。专家是条件循环宏节点，尚未按真实m_e展开；这些数量不是实际kernel数、事务数、已执行op数或整个agent任务规模。任务控制图有合法循环，标记为CONTROL_FLOW_TEMPLATE_WITH_LOOPS_NOT_EXECUTABLE_DAG；只有观测到的有限turn/token展开后才能成为执行DAG。

本轮未获取具体SWE任务或自主输出，不虚构读→改→测次数、专家ID、并发、物理地址或周期。图里的读/搜索/编辑/测试是可选工具命令类型，不保证每个任务按固定顺序发生。

## 1. 源码与模型身份

模型使用已核验目录/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B。读取config、index及16个safetensors头部，不求值权重。MODEL_HEADER_AUDIT.json记录全部参数元素合计30,532,122,624，dtype均BF16，净张量载荷61,064,245,248 B。权重分片文件61,066,575,648 B，整个模型仓库26文件61,084,187,391 B；头部开销、配套文件与净张量载荷不得混计。

结构参考固定Transformers v4.51.3的Qwen3-MoE实现，而不是当前113已安装4.40.2的运行证据。本地源码SHA见SOURCE_MANIFEST.json。模型配置为48层、H=2048、Q头32、KV头4、head_dim128、专家128、Top8、专家中间维768、词表151936、untied LM head，无shared expert。参考代码中Q/K RMSNorm learned scale各为[128]并跨head共享。

旧qwen3_30b_a3b_v3_5_mapping/build.py把Q/K scale按head重复计入，得到30,532,331,520参数，多计208,896个。本轮以头部和新公式一致值为准；未修改旧脚本/历史产物。这个差异很小但必须纠正，不能继续将旧公式称精确参数量。

来源：[官方固定版本模型代码](https://github.com/huggingface/transformers/blob/v4.51.3/src/transformers/models/qwen3_moe/modeling_qwen3_moe.py)、本地source/modeling_qwen3_moe.py:137—219（attention）、223—289（专家/router）、292起（RMSNorm）、312起（decoder）、410起（RoPE）、946起（LM head）；source/MODEL_HEADER_AUDIT.json；../mini_swe_hiband_semmoe_plan_20261026_v1/ASSET_MODEL_VERIFICATION.json。

## 2. 应用层任务拆分

Host负责issue/repo/base_commit加载、history/chat template/tokenizer；模型调用包括未缓存prefill、LM head和首个采样token，之后视输出继续decode；完整消息交给parser，合法非终止命令交外部CPU/container，完成后把stdout/stderr/exit code作为下一轮输入。格式错误可直接产生反馈，无工具执行；提交、预算超限、工具失败和超时都有终止分支；最后由官方harness验证patch。

CPU工具执行、镜像启动、文件系统和测试不是NPU算子。工具完成必须是下一turn的外部release gate。多任务不强制同到达。KV是否跨API调用复用未知；每轮可能重新prefill已见历史，实际发生的重算要计入。

首个输出token来自prefill最后有效位置的logits，不应额外伪造一次“first-decode forward”。后续decode输入上一输出token；任务是否调用模型多次、生成多少token、使用何种采样必须从实际后端确定。源码logits_to_keep=0可能计算全部位置，因此LM head位置数J保留为变量，不能默认总是1。

来源：../mini_swe_qwen3_preflight_20261026_v1/official_snapshot/src/minisweagent/agents/default.py的run/query/execute_actions；固定源码提交04d809ceab9df28f9adaed044884180159172930。生成策略来自后端GenerationMixin/agent模型适配，尚未固定或运行。

## 3. 模型算子拆分

以单session、未缓存token数T、已有cache长度P表示，prefill允许分块且P可非零，常规decode取T=1。完整层链为：

RMSNorm → Q/K/V投影 → Q/K逐head RMSNorm → RoPE → KV追加/读取 → GQA分块QK → scale/mask/softmax → AV → O投影/TP求和 → 残差 → MoE RMSNorm → router GEMM/FP32 softmax/Top8/归一化/回写隐藏dtype → pack/dispatch → 活跃专家权重驻留门控 → gate/up GEMM → SiLU/逐元素乘 → down GEMM → 最终路由权重乘 → 返回/index_add → hidden同步 → 残差。

全模型还包括embedding lookup与同步、每次forward共享的RoPE cos/sin生成及分发、48层后的final RMSNorm、位置选择、LM head、logits传输/分布式选择、采样与停止判断。embedding/head/vector不省略，训练loss不加入推理主路径。若output_router_logits=True触发辅助负载均衡计算，计为诊断分支；建议在实际dispatch点hook，开销另测。

关键维度：Wq[4096,2048]，Wk/Wv各[512,2048]，Wo[2048,4096]，router[128,2048]；每专家gate/up各[768,2048]，down[2048,768]。令m_e是当前有效token分配到专家e的数量，sum_e m_e=8T；只执行m_e>0的专家。实际专家权重读取可因cache与复用不同，不能把128个专家都算作每token执行。

QK和AV的有效因果pair数各按A=T*P+T*(T+1)/2，MAC各为32*128*A；实际tile padding/mask后kernel工作量可能更大。完整attention score只标逻辑尺寸[32,T,P+T]，不宣称整矩阵写HB。FlashAttention/SDPA与目标tiled lowering不是相同kernel，需要数值与访存验证。

## 4. 对应目标架构

目标保持规范V3.6：16个NPU、4×4 mesh＋gateway、每NPU 4 MiB SRAM/8 SRAM Bank、64×64阵列、FP16 2048 MAC/cycle且FP32累加、FP32 vector/reduce各16 ops/cycle；16个512 MiB CH，每Ni↔CHi整体25.6 GB/s，规范32 B事务。4个逻辑投影Bank、16个decoded DRAM Bank、8个SRAM Bank分开。上述是规格，不是本负载性能认证。

矩阵运算映射到NPU阵列候选；RMSNorm、RoPE、SiLU、softmax、TopK、逐元素、归约/加权合并映射到FP32 vector/reduce的软件lowering候选。exp/rsqrt/sin/cos/TopK/scatter不存在已校准原生指令时延，不能按16ops/cycle直接当完整特殊函数吞吐。BF16也不能由FP16阵列规格推定支持。

注意力采用TP16候选：rank r负责Q头2r和2r+1，读取KV头floor(r/4)。因为只有4个KV头，采用每KV头在四rank复制，K/V projection和KV cache均增加到4份。每rank的O投影生成partial，通过NoC求和；非线性与残差在复制的hidden上执行。

MoE采用EP16，基准p_l(e)=e mod16，每层每rank8专家。router暂放N0只算一次；N0传递route metadata到唯一token origin o(t)=t mod16，origin将每个逻辑assignment只dispatch一次；专家在owner处理后回origin合并，再同步hidden给下层TP组。该origin/collective是透明的候选设计，不是Sem-MoE官方在线算法。Sem-MoE只能在合法容量下改变p_l(e)/请求调度，不能改变模型图或偷看未来实际路由。

CPU/gateway/PCIe处理工具与输入/输出/后备搬移。HB保存驻留权重和KV，SRAM只放tile和活跃工作区。内存和NET均需真实完成回调后释放消费者。模式、应用阶段、BSA/BGA和scope分别记录；图不预设HIC重叠或动态HiBand收益。坐标图未规定gateway接入哪一mesh节点，不虚构该端口。

来源：../whisper_operator_inventory/target_architecture_v3_6/target_architecture_v3_6.yaml与README.md；MAPPING.json。图中具体TP/EP复制、router/origin选择属于本轮候选，尚非已有运行事实。

## 5. 容量与分块核查

单专家BF16权重9,437,184 B（9 MiB），超过4 MiB SRAM，必须按矩阵tile流入；每rank全48层专家合计3,623,878,656 B（3456 MiB），远超512 MiB CH。64×64×64示例tile仅输入8 KiB、权重8 KiB、FP32累加16 KiB；它不是完整峰值SRAM证明，双缓冲、多个操作、KV和route workspace仍需生命周期审计。

TP16候选把K/V projection额外复制603,979,776 B，并复制norm向量6,328,320 B，物理权重载荷合计61,674,553,344 B。无复制时全模型KV每缓存token98,304 B，候选复制后393,216 B，即每rank每缓存token24,576 B。

示例单session、4096缓存token时，每rank KV 96 MiB，全模型1.5 GiB。这是解析示例，不是已观测SWE上下文。若假定nonexpert全驻留并预留未验证的32 MiB runtime，rank0还有15个完整专家cache slot，其他rank代表还有18个；16384缓存token时该候选仅nonexpert+KV+reserve就超512 MiB。实际prefill chunk的瞬时工作区不在这个简化cache预算内。

更基础的阻断是：61 GB unique BF16载荷大于8 GiB HB＋8 GiB目标host。服务器256 GB RAM不等于目标host容量。即使逐层分页，仍须明确外部存储及其服务，或另立扩大host容量的敏感性配置，不能把未知后备来源当零成本。当前无完整可部署驻留集，不能产出带绝对周期的目标IR。

来源：CAPACITY.json、TILING_CANDIDATE.json和source/MODEL_HEADER_AUDIT.json；所有新capacity例子为公式复算，不是仿真。

## 6. 验收与下一步

已完成：源码/头部绑定、算子维度与参数公式、两份48层符号DAG拓扑检查、Q头覆盖/KV组/专家owner分区检查；三图已渲染读图，消除标签遮盖。VALIDATION.json的PASS_STRUCTURAL_ONLY不升级为数值/事务/执行PASS。

尚未完成：BF16算术/转换、逐rank峰值工作区、外部存储/host服务、具体物理地址、完整32 B事务、collective算法、真实m_e、任务/镜像、GPU功能、设备执行和热模型。后续按REPLAN.md先补这些结构合同，再启动相应范围的运行。

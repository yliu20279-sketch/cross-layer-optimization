# 两模型P0-1b／P0-1c接入续作 v4

日期：2026-11-02。状态：**新版实验计划已保存；P0-1c身份门控复用判定完成；P0-1b仍PARTIAL。正式性能实验未启动。**

## 1. 本轮范围

只负责Qwen3-30B-A3B BF16与Qwen1.5-MoE-A2.7B-Chat-GPTQ-Int4离线解码FP16。世界模型与mini-SWE-agent工作线未接管、未启动或停止其后台任务。

已先保存[新版两模型实验计划](../CA_两模型实验计划_20261102_v4.md)，按setup、性能、supporting、规模/敏感性及cost组织。保留原计划与v3结果。当前工作目录为独立v4目录，113同名路径位于 `/mnt/sda1/h3240101068/ca_semmoe_hiband_native_20261102_v4`。

本轮将CPU功能载荷与实际内存/网络控制分别做了接入；**两者尚未在完整目标层中耦合**。CPU动态库不冒称NPU primitive，主机内存拷贝不冒称目标NoC，分析式计算的Ramulator/PopNet探针不冒称完整模型功能运行。

## 2. 新增实现

| 文件 | 实际改动 | 当前边界 |
|---|---|---|
| `models/qwen3/build_graph.py`、`models/qwen15/build_graph.py` | 增加实际执行MoE入口，不再只有语义图返回 | 输入为已经归一化的MoE入口；不含完整attention/residual/norm/KV |
| `core/live_moe.py` | 真实router权重、自主TopK、profile专家归属、dispatch/专家/加权combine、shared TP与SAG实际载荷消费 | CPU功能候选，未对原模型完整oracle认证 |
| `core/native_payload.py`、`runtime/payload_kernels.cpp` | 编译CPU FP16/BF16 codec、线性投影、bias前置于最终舍入、FP32归约和实际载荷拷贝 | 非目标NPU算子与成本模型；不替换原Qwen3 BF16 primitive合同 |
| `core/payload_collectives.py` | SRS/SAG按实际token槽位、各peer与有效字节执行载荷移动和归约 | 主机完成回执，非目标网络时序 |
| `models/qwen15/fp16_math.py` | 显式复用旧已冻结FP16软件数学微程序 | 保留原来源；不是新数学算法或GPU逐位认证 |
| `models/qwen15/projections.py` | 允许profile训练的专家归属替代静态e%4参考；标出归属来源 | 旧4992条静态投影表不再暗示适用于任意Sem布局 |
| `runtime/live_controls.h` | 有限分区物理页映射、固定页保护、双射、代际、inflight排空；带宽预算、切换延迟与包完成控制 | 页安装为静态入口；不含完整权重搬移/缓存维护与动态分页认证 |
| `runtime/native_live_controls.cc` | 页映射实际作用于Ramulator提交地址；预算与排空切换实际约束PopNet发包 | 分析式计算仍保留；项目注入预算模型，不等同作者HIC/SOR/split-Benes |
| `tools/classify_reuse.py`、`REUSE_DECISIONS.csv` | 逐case门控复用判定，缺身份字段拒绝周期晋级 | 非全事件重放；不虚构尚未冻结的新B图/输入/初态哈希 |

全部20项清单见[实现账本](IMPLEMENTATION_STATUS_v4.csv)。账本的implemented仅指注明范围的实现，不表示完整目标验收。

## 3. 已确认的检查

### 3.1 编译与软件检查

最终113 `runtime/build_02`在33个冻结后端链接输入SHA匹配后构建。候选可执行SHA为 `460749da38cffbbab487deda68eef9ccc5a3d44303308bd6d11e1e601816b588`；CPU载荷库SHA为 `898e7d47c1348749a3da7f8305880ef2b922afa6256ad4c94d47571f0c33902f`。

113共28项检查通过、0跳过；本地24项通过、4项因无Linux动态库明确跳过。编译控制探针12项拒绝检查通过，覆盖非法映射、固定页移动、别名、跨页/旧代际、重复回调、未排空切换及预算约束。

来源：[最终构建](evidence/REMOTE_BUILD_LIVE_02.json)、[113软件回执](evidence/REMOTE_SOFTWARE_CHECKS_v4.json)、[本地回执](evidence/SOFTWARE_CHECKS_v4.json)。

### 3.2 实际权重的CPU功能接入

- Qwen3：18867个BF16对象的header/形状/偏移绑定，跨16分片142对象426个实际字节跨度；本轮不是重新哈希全部61GB权重。
- 最终诊断每模型一个归一化输入token，真实权重执行Qwen3的25个投影调用、Qwen1.5的26个调用，含自主router和shared TP；输入是明确的诊断向量，非自然benchmark或未见测试集。
- FP16的63488个有限编码、BF16的65280个有限编码，解码和回编码逐位检查通过；另外检查NaN/Inf类别，不宣称NaN payload编码全部逐位保留。
- 实际CPU载荷集合：TP4/TP16，各5个token、hidden2048；分别30/150个远端载荷传输、122880/614400有效字节，槽位恢复及数值检查通过。
- Qwen1.5层0 Q/K/V三项2048×2048投影实际使用非零bias；各抽取3列与独立标量FP32计算比较。另有专门反例确认bias位于最终FP16舍入之前。
- Qwen1.5最终路径保留FP16路由权重、逐slot FP16加法、shared每rank FP16输出→固定FP32求和→FP16、共享门控的FP16边界。

上述不构成完整原模型输出、GPU逐位、完整attention或目标NPU时序通过。Qwen3的新增CPU功能核尤其不能替代原BF16精度合同；其全模型数学等价仍待核验。

来源：[最终CPU功能回执](evidence/REMOTE_PAYLOAD_AUDIT_v2.json)。回执记录精确使用的core/models源码SHA，本地已与实际编译/运行来源逐项匹配。

### 3.3 真实后端控制检查

最终build02执行了独立小探针：4个诊断region，3笔实际Ramulator事务、7个PopNet包、1次模式切换，全部回调排空；两笔读实际地址为8186/8，对应原逻辑4090/4104，证明映射被真实后端消费。注入占用3104字节，含3100有效通信字节及flit填充。

本地重新核SHA并从原始CSV独立恢复3事务/7包的issue—callback配对、时序、地址及排空。初版与最终版各一次小探针，均不是模型或正式性能实验，不把两次叫作系统反馈收敛。

来源：[最终真实控制回执](evidence/REAL_CONTROL_PROBE_02.json)、[本地原始日志独立检查](evidence/LOCAL_CONTROL_AUDIT.json)、[最终原日志](remote_control_02/control_probe_02/out/events.csv)。底层summary沿用旧后端候选状态名称，该名称不证明身份映射或模型完整通过；以本节实际范围及回执字段为准。

## 4. P0-1c复用结论

113只读重新核验Qwen1.5的100主运行＋25反事实，以及Qwen3十个可发现配对目录，并重建计划所引用七组摘要。核对读取约381.8MB；874项与既有期望SHA匹配，176项只计算现值、无旧期望，不能写成1050项全部“与冻结值一致”。无MISMATCH/MISSING/读预算延后项。

| 资产 | 结论 |
|---|---|
| Q15 100＋25 | 旧INT4分配/采样机制合同与新解码FP16不同，binary不同且完整新B身份字段尚缺；周期不复用。25组反事实总周期差仍全为0 |
| Q3七组 | 原始端点周期和摘要差值重建一致，负例保留；扩容case与512MiB分区不同，旧代理非新BF16 B；周期不晋级 |
| Q15 183个旧投影 | 沿用v3逐位一致的载荷复用结论；专家归属需明确静态参考或profile，不继承旧周期 |
| 旧Q15四请求数值 | 仅原层0、原输入、原FP16容差范围，不转成完整模型质量结论 |
| 旧原生后端 | 33链接对象与接口方法可复用；新的布局、调度、控制和输入不能继承旧周期 |
| 旧Q3 FP16、阶段1/2及288case | 方法、已见DEV和历史正负例分账；不替代BF16或新TEST |

当前0个case允许晋级为新组合基线主性能。完整同合同条件不满足时，停止昂贵的周期晋级审计是合理的；没有因此重放全部旧事件。P0-1c完成指已对指定已知资产作出可追溯的复用判定，不是旧资产全部重新运行认证。

来源：[原始只读审计](evidence/REUSE_FRESH_RAW.json)、[复用判定](evidence/REUSE_DISPOSITIONS.json)、[逐case CSV](REUSE_DECISIONS.csv)、[七组原摘要快照](evidence/Q3_SEVEN_SOURCE.csv)。

## 5. P0-1b仍未完成的部分

| 顺序 | 剩余工作 | 对应ID与位置 | 完成依据 |
|---|---|---|---|
| 1 | 完整attention、residual/norm、KV输出接到MoE，不能用现成fixture代替 | Q3-02、Q15-03；两模型build_graph及实际目标入口 | 真实prefill/cached decode连续调用与输入输出/路由证据 |
| 2 | 将数值primitive、SRS/SAG载荷、内存与NoC完成接回同一目标活动域 | Q3-03/04、C-01；payload_collectives、目标primitive/服务及native入口 | 不能用CPU算完结果后另跑独立时序冒充耦合；目标数据依赖和回调可追踪 |
| 3 | Q15全目标TP/PP、72 QKV bias及精度边界 | Q15-03及算子绑定 | 不仅单个CPU投影抽样；全实际调用链消费 |
| 4 | 完整迁移/缓存版本、代际与动态HB/KV/激活/SRAM生命周期 | C-05及实际allocator/cache | 真实数值载荷安装/维护/回收、容量和旧代际拒绝；不只地址标签 |
| 5 | CPU、PCIe、安装/切换、维护及完整算子成本 | C-04及实际控制/成本服务 | 相同目标时钟域，成本完整且不重计；HIC等未实现部分按实际方法命名 |

源码门仍保留Q3-02/03/04及C-01/04/05、Q15-03及C-01/04/05缺项。未因CPU检查或真实小探针通过而将其改成implemented/verified。两模型performance_ready仍false，P0-2尚未启动。

来源：[机器状态](STATUS.json)、[当前准入](contracts/gates.json)、[实现账本](IMPLEMENTATION_STATUS_v4.csv)。

## 6. 失败与中间版本

首次有界CPU检查无完成回执，SSH返回1且未保存stderr，原因未确立，不宣称数值失败；后续修正真实dense布局标签，并将BF16随机I/O限制为跨分片样本。记录见[首次记录](evidence/PAYLOAD_ATTEMPT1.json)。

最终检查一次在写回执时因路径变量被输出字节覆盖而报AttributeError；28项测试已通过，数值脚本各检查走完但回执未写成功。已修正变量并重新生成最终回执；原错误日志留在[首次最终检查stderr](remote_receipts/evidence/PAYLOAD_FINAL.stderr)。没有删除中间FP16运算边界版本或将其当最终合同。

## 7. 交付说明

本地及D盘保存代码、合同、旧结果复用索引、最终构建回执及有限探针原日志；约28.6GB的Q15 FP16权重和Q3权重仍在113，未重复下载。最终candidate二进制也留113，交付其SHA与源码快照。全部交付成员另附DELIVERY_MANIFEST.json。

本轮未做正式性能比较、完整模型前向、新GPU采集、世界模型/agent任务或物理芯片实验。下一项实质工作是表5的完整目标执行耦合，不是扩大性能矩阵。

原资料与上一轮来源：[v3报告](../P0_FP16收敛交付_20261102_v3/REPORT.md)、[旧FP16物化](C:/Users/21747/Documents/跨层优化/selector_real_fp16_materialize_v1/REPORT.md)、[旧联合后端](C:/Users/21747/Documents/跨层优化/selector_fp16_joint_native_v1/REPORT.md)、[本地v3工作报告](C:/Users/21747/Documents/跨层优化/ca_semmoe_hiband_fp16_20261102_v3/REPORT.md)。

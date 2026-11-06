# P0-1a—P0-1c 推进报告

日期：2026-11-02（Asia/Shanghai）。目录：`ca_semmoe_hiband_baseline_v2`。

## 1. 判定先行

本轮有实际代码和证据进展，但**不能标为P0全部完成或组合性能基线通过**。

| 阶段 | 状态 | 已完成 | 尚未完成 |
|---|---|---|---|
| P0-1a 合同收敛 | PARTIAL | 两模型机器合同、字段/拒绝准入规则；Qwen3全部16分片SHA256及索引/头/元数据绑定；Qwen1.5搜索与排除变体 | Qwen1.5原版BF16资产未找到；Qwen3上游不可变revision未证实；两模型真实运行栈/容量/成本绑定 |
| P0-1b 实现修正 | PASS_SOFTWARE_REFERENCE_ONLY / PARTIAL_NATIVE | 新隔离软件模块；本地与113均15组软件检查通过；两模型因果调度、split拒绝、TP语义、精确对象/地址接口、时间CA、模式/成本拒绝控制 | 原生SRS/SAG、全部算子与内存生命周期、真实CPU/缓存/版本/HiBand成本、真实CA sidecar及decoder接入；未形成可执行完整目标基线 |
| P0-1c 证据复用 | COMPLETE_CLASSIFICATION_SCOPED | 旧Q15 125case与25配对算术、750项冻结哈希匹配、旧binary/库身份；Q3原7组小审计全匹配；分档复用判断 | 未重审全部原始事务/事件载荷；不允许将旧周期移入新BF16组合主表 |

原实验目录、PASS/失败及计划文件未覆盖。11个关键历史本地文件逐项核对原字节SHA256不变。未停止/重启其他后台任务。本轮新增目标原生、GPU、模型推理、路由采集和性能矩阵运行均为0；P0-2未开始。元数据搜索、文件哈希和合成软件检查分别记账，不算真实负载验证。

## 2. P0-1a：具体证据

### Qwen3

已对113 `/mnt/sda1/models/Qwen3-30B-A3B-modelscope` 的16个实际safetensors分片逐一读取SHA256。分片文件总量 **61,066,575,648 B**；18,867个张量的有效数据总量 **61,064,245,248 B**。两者差额是文件头等开销，不混作参数字节。全部张量头dtype为BF16；index的tensor→shard绑定和total_size逐项对应。tokenizer.json、tokenizer_config.json及config等小文件全量哈希已记录。

哈希进程使用idle I/O、nice19，顺序读取，耗时约357.84秒；未将权重加载到torch或执行模型。文件大小与修改时间和先前观察对应；不把这项检查称为数值forward。

冻结内容清单指纹：`65ed1e6dad7467f2d9e620c79f9b639b9eeae2b42579d6795224707cc077b859`。其定义为规范化文件名/大小/各文件完整SHA256清单的SHA256，不是伪造的HF commit，也不是单个拼接权重文件SHA。上游revision仍为null，内容快照ID单列。

来源：[全分片哈希](evidence/Q3_FULL_CHECKPOINT_HASHES.json)、[分片头与原始核查](evidence/REMOTE_CURRENT.json)、[张量清单](contracts/qwen3_tensor_inventory.json)、[来源文件状态](evidence/Q3_SOURCE_FILE_STATS.json)、[Q3合同](contracts/qwen3.json)。

### Qwen1.5

按用户要求在本地和113查找，不下载、不替换模型：

- 本地：所选模型缓存、Downloads、项目及D盘electronic_science范围遍历33,586个目录，读取166份config；所选范围已遍历完，仅识别到Chat-GPTQ-Int4变体。某些缺失root、排除项及symlink边界见清单。
- 113扩大搜索：30秒、28,293目录、11份config，达到时间上限；定向补查跳过实验results/runs/Trace后，40秒、54,654目录、11份config，仍达到时间上限，仅识别到已知Chat-GPTQ-Int4。

结论是“记录范围内未找到原版BF16 checkpoint”，不是全服务器或所有压缩包绝对不存在。现有Chat/GPTQ保留为变体证据，不改名成原模型，不恢复旧TEST的未见身份。资产缺项进入机器合同和准入拒绝结果。

来源：[本地搜索](evidence/LOCAL_MODEL_SEARCH.json)、[113扩大搜索](evidence/REMOTE_MODEL_SEARCH.json)、[113定向补查](evidence/REMOTE_MODEL_SEARCH_TARGETED.json)、[资产搜索合同](contracts/original_model_search.json)、[Q15合同](contracts/qwen15.json)。

## 3. P0-1b：实际实现范围

| 模块 | 实现 | 限制 |
|---|---|---|
| core/scheduling.py | profile/eval显式分离、source/token哈希去重；平衡专家放置；只用token与决策时可用信息；真实router结果另在完成后用于dispatch | token-affinity-only项目消融，未实现论文2-gram；不是作者代码等价 |
| core/capture.py | 原模型、BF16、checkpoint/tokenizer/revision身份缺项及Chat/GPTQ替代拒绝 | 不采集、不加载模型；真实原模型采集仍缺 |
| core/collectives.py | SRS/SAG的token身份、rank分配、显式加法语义与恢复 | 整数小样本语义参考，不是GPU数值归约或融合目标opcode |
| core/graph.py、models/ | 两模型Top8/Top4、shared路径语义、slot/权重、真实peer、local/global及生产者依赖 | 不是完整attention/FFN原生lowering、PP时序或连续层数值认证 |
| core/memory.py、models/shared.py | 真实shape/dtype字节、有效尾字节、跨页拆分、生命周期/别名/容量约束、固定对象与分区页池双射 | 未接全部实际BF16 operand I/O、动态paging和原生allocator |
| core/coaccess.py | 成功accept→callback历史区间、跨独立请求逻辑页边、Heat/CA词典序目标、固定评价次数与有效字节改动预算 | 区间不是Bank驻留；真实事件sidecar与后端decoder尚未绑定；无真实CA收益 |
| core/runtime.py | 显式tx参数、时钟向上取整、模式预算/排空参考、缺成本/跨时钟域/重叠求和拒绝 | 不是作者HiBand scheduler或实际CPU/缓存/切换计时服务 |
| core/reuse.py | 12项必要身份比较；双方空字段不等于匹配；精度或配置不同则拒绝新周期复用 | 不替代全部原始事务审计 |
| core/readiness.py、runner.py | 单一合同、证据路径/hash核验、缺资产/原生能力/容量/成本时拒绝；无模型/模拟器启动接口 | 只允许check-only，不存在自动run-all |

20项修正逐项状态见[IMPLEMENTATION_STATUS.csv](IMPLEMENTATION_STATUS.csv)。REFERENCE_IMPLEMENTED表示对应软件参考已实现，不表示其native部分完成。Q3-04、Q15-04/05、C-01/04仅接口或部分完成；其余仍须按原生验收约束接入。未因写出模块就把capability设为verified。

15组软件检查包括未来路由扰动不影响预调度、split/源重复拒绝、原模型替代拒绝、未知token、SRS/SAG在27种分配下恢复、两模型TopK/shared语义、全部peer字节守恒、跨页/生命周期、独立两两区间重算、坏callback拒绝、优化双射/预算/确定性、模式排空、缺成本与重叠成本拒绝、未知身份拒绝复用、真实候选合同拒绝原生准入。全部是小型fixture，不是15组真实模型实验。

本地15/15通过；113 Python3.8.10的新revision_02也15/15通过，35个上传文件逐项SHA256一致。最初14项检查版独立保留，未覆盖。

来源：[本地软件检查](evidence/SOFTWARE_CHECKS.json)、[113最终检查](evidence/REMOTE_SOFTWARE_CHECKS_v2.json)、[上传文件清单](evidence/UPLOAD_MANIFEST_v2.json)、[README](README.md)。

## 4. P0-1c：旧证据复用核验

### Qwen1.5旧125运行

从113自身provenance与目录发现读取100个主运行及25个counterfactual的launch、run_manifest、audit、graph_manifest、modes、ops图以及配置。750项与原冻结预期SHA匹配；125份运行ramulator配置取得当前哈希但原evidence_manifest未提供对应预期，记HASHED_NO_EXPECTED，不伪称冻结匹配。

旧popnet及libramulator二进制全量哈希与原manifest相同。125份完成元数据均PASS、completed=operations、causal_violations=0；25组normal/counterfactual的周期差重新计算均为0。这仍是旧理想W4/工作集与采样代理合同下的结果。

本轮只读哈希约381,812,961 B，未全量重读125个原始bank/event载荷，不宣称重新复算所有事务、归因算法或图的每一条依赖。原有全量审计结论沿原报告范围保留。

### Qwen3旧配对

远端自身目录定位到10个配对根，其中包含原7组之外的c2其他方案；不扩大新实验计划。本地原7组provenance的小型validation与paired_audit哈希全部匹配；c2的paired_audit位于共同父目录，首次自动查找位置不对，后续只读补查并匹配，失败记录保留。对应launch图与二进制身份亦有只读记录；原始bank_requests.csv完整载荷未重审。

### 分档判定

- 方法/工具可在审查后复用。
- 上述正、零、负结果可作为明确旧合同下的历史证据。
- **本轮没有任何旧周期获准进入新BF16组合主表**：精度/对象/执行路径不同，且新合同还有空身份字段；两个None不视为匹配。
- stage1桥身份、stage2冻结起点/最终状态等小证据已读取，不升级为完整系统或新留出认证。

来源：[只读核验原文](evidence/REMOTE_REUSE_AUDIT.json)、[Q3父目录补查](evidence/Q3_PARENT_AUDIT.json)、[复用决策](evidence/REUSE_DECISIONS.json)。

## 5. 远端交付、隔离和失败记录

远端候选源码：`/mnt/sda1/h3240101068/ca_semmoe_hiband_baseline_20261102_v2/revision_02`。初次上传包与后续revision_02分别保存；只运行合成软件检查，不运行旧runner、模型或模拟器。

只读脚本第一次因远端Python3.8不支持Path.is_relative_to失败；修正后发现远端没有本地同路径provenance摘要，改为113自身索引发现、返回后本地匹配。原错误不改称实验数值失败。

一次携带本地provenance的上传被自动审批拒绝，理由是用户当时尚未明确允许外传内部元数据；当时采用不上传本地证据的只读替代。用户随后明确允许发送至113，之后只上传本任务新隔离修正包，不覆盖历史。

来源：[失败1](evidence/READ_AUDIT_ATTEMPT1_FAILURE.json)、[自动审批记录](evidence/READ_AUDIT_REJECTION.json)、[历史源码保留核验](evidence/HISTORICAL_SOURCE_PRESERVATION.json)。

## 6. 剩余工作与范围

P0-1a仍缺Q15原版资产与Q3上游revision来源；两模型运行栈、资源/精度/成本合同尚未闭合。P0-1b仍缺原生SRS/SAG、全部目标算子与真实I/O/生命周期/控制成本，以及CA sidecar/decoder接入。Q15资产缺失会阻止该模型数值/目标验收，但不能拿它解释Q3全部独立实现缺口。

机器拒绝准入明细：[contracts/gates.json](contracts/gates.json)。未知项不填虚假值，不自动下载新权重、不换Chat模型、不扩大HB或host容量、不把旧FP16/W4结果拼成BF16通过。

下一步应继续补原生适配与来源身份；涉及目标数值/时序运行时再进入P0-2。本轮不提前执行P0-2，也不作策略净收益结论。

## 7. 依据与复核入口

- [本轮机器状态](STATUS.json)
- [Qwen3合同](contracts/qwen3.json)、[Qwen1.5合同](contracts/qwen15.json)、[运行合同](contracts/runtime.json)、[CA合同](contracts/ca.json)
- [原实验计划修订版](../CA_SemMoE_HiBand_实验计划_20261102_v2.md)：D盘交付中的上级目录链接
- [合同修正依据](../合同收敛与修正清单_待审议_20261102_v1/合同收敛方案与实现修正清单_待审议.md)：D盘交付中的上级目录链接
- [全部文件清单](DELIVERY_MANIFEST.json)：逐文件SHA256，不含自身哈希

报告只覆盖实际查阅及列出的证据，不声称本地/113所有Trace、归档和历史聊天均已通读。
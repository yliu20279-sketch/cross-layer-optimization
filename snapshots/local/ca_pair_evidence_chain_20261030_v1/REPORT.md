# CA页对→等待→消费者证据链

日期：2026-10-30，Asia/Shanghai。状态：PASS_CONTROLLED_TRACE_CHAIN_SCOPED。

## 结论和来源边界

已有数据可以闭合“共同在途、原来同Bank→记录到跨owner同Bank等待→CA分Bank→同一逻辑读取等待下降/回调提前→群组消费者及整段更早完成”的受控观测链。

这不是“两页独立干预的因果效应”证明。采用历史 `qwen3_strategy_native_v1/evidence_v1` 的 `coaccess_witness_rr` 与 `coaccess_witness_coaccess`，基线是RR布局，不是自然分配器O，也不是上一条举例的qwen3_eC O_fixture。原eC页对23378/23442的CA逐事务文件在所查本地位置缺失，本报告没有借其他实验日志替它补链。

场景为192个4KiB页、16个decoded Bank、partition0、合成owner标签、每op MLP1、窗口间显式屏障。不是自然完整MoE或实际四用户请求；不能将本结果替代自然实验。此次只读取历史文件，没有SSH、新采集、仿真、修改算法或论文。

## 1. 页身份和同Bank关系

取第一个窗口的op0/op1，逻辑页23360/23376（张量内页0/16），owner标签0/1。每页完整读取4096B，拆成16笔256B事务。

|布局|A目标frame/Bank|B目标frame/Bank|
|---|---|---|
|RR基线|23360 / Bank0|23361 / Bank0|
|CA|23360 / Bank0|23377 / Bank1|

页A物理frame保持不变；页B更换frame。Bank来自保存事务中的bankgroup/bank及实际地址位，decodedBank=4×bankgroup+bank，另由二进制页表与逆映射交叉核对。不是仅比较计划Bank标签。

## 2. 实际读取重叠，而不只是同窗口

检查两页各自页内offset256的同一逻辑事务。这里“重叠”指submit到callback的在途区间重叠，不是同一个Bank能同时执行两条读命令。

|布局|页A的submit→callback（cycle）|页B的submit→callback（cycle）|在途交集|
|---|---|---|---|
|RR|45→236.25|50→241.25|50→236.25，共186.25 cycle|
|CA|45→72.5|50→77.5|50→72.5，共22.5 cycle|

两套运行中该对事务submit分别均为45和50，controller arrive分别均为36和40 tick。因此该局部对照不是靠把页B延后提交来消除重叠。

## 3. 原布局有明确的同Bank等待，CA后下降

下表对应同一offset256读取；controller计数单位为tick，submit/callback单位为cycle，不混加。

|量|RR页A|CA页A|RR页B|CA页B|
|---|---:|---:|---:|---:|
|decoded Bank|0|0|0|1|
|controller arrive tick|36|36|40|40|
|first issue tick|139|39|174|43|
|controller queue ticks|103|3|134|3|
|cross-owner same-Bank wait ticks|14|0|120|0|
|callback cycle|236.25|72.5|241.25|77.5|

页B的row=365、column=17、row_status=1、row_command_ticks=0、completion_ticks=19在前后均相同。这避免将该笔交易的变化简单解释为其自身row-command耗时缩短，但不隔离全局row状态、调度及其他访问的作用。

全部16笔事务求和，页A对应跨owner Bank等待210→0 tick，页B为1813→0 tick。完整4KiB LOAD事件完成时间分别由2914/2919提前到493/498 cycle。详情见PAIR_ALL_TRANSACTIONS.csv和PAGE_OPERATIONS.csv。

日志没有记录逐tick阻塞者transaction ID，所以不能把页B的120 ticks全部精确归给页A。它认证的是页B处于同Bank竞争群组并记录到跨owner同Bank等待，而不是仅这两个页之间独占的等待账本。

## 4. 等待改善传播到真实依赖消费者

保存DAG中op0—11均是op12 `window0_barrier` 的前驱，op12又是下一窗口op13的前驱。两布局图哈希完全相同。

|事件|RR（cycle）|CA（cycle）|提前|
|---|---:|---:|---:|
|页A完整LOAD done|2914|493|2421|
|页B完整LOAD done|2919|498|2421|
|窗口最晚前驱op11 backend_done|3056.25|545|2511.25|
|窗口最晚前驱op11 modeled_gate|1920|1920|0|
|窗口最晚前驱op11 done|3057|1920|1137|
|op12 barrier ready/start|3057|1920|1137|
|op12 barrier done|3058|1921|1137|
|下一窗口op13 ready/start|3058|1921|1137|

全部读取的回调完成与事件完成规则独立核对：`done=ceil(max(last_callback, modeled_gate))`。屏障ready等于其全部前驱done的最大值，下一窗口ready等于屏障done。

因此这里不是只看两页回调更快后就推测消费者更快：保存的依赖与消费者时间实际一致。与此同时，CA后该窗口的最晚读取已被原有1920 cycle gate限制，不能将2511.25 cycle的backend提前全算成窗口加速。

页A/B不是窗口唯一前驱，真正决定屏障就绪的是op11。上述1137 cycle是整组12页布局变化的效果，不是页A/B独立贡献。

## 5. 整段受控完成周期

|布局|总周期|op数|依赖边|事务数|总读取字节|
|---|---:|---:|---:|---:|---:|
|RR|51835|208|372|3072|786432|
|CA|30736|208|372|3072|786432|

整段减少21099 cycle，即40.704157%。这是该受控布局整体收益，不是自然模型、原eC场景的34.1078%，也不是单对页的加速比。

## 6. 必须同时保留的反例

同一页B的offset0事务，其跨owner Bank等待也从13降到0 tick，但callback均为50 cycle，未提前。该笔事务row-command与调度变化抵消了等待计数改善。

所以不能写“每一笔同Bank等待下降必然带来回调提前”，也不能将累计等待下降直接等同整段周期下降。本报告选用offset256展示有传播的观测，同时保留offset0反例，不隐去不支持简单推断的交易。

## 7. 审计、复现与不能写的结论

audit_chain.py只读取历史文件，向本目录写分析结果。18份原始图/页表/launch/事务/事件/运行记录/源码/协议文件与原manifest SHA256一致，并复制小型来源快照。两套页表均为131072个frame的完整置换；全部3072笔事务逆映射后的逻辑地址、offset、字节和owner一致。208事件、372依赖、每op16笔/信用1、回调到完成规则及屏障传播均检查通过。除输出位置、映射表及各自空trace路径外，保存的启动控制与命令一致。

可写：在该人工机制合同中，CA将一组原本同Bank的重叠读取分散到不同Bank；对应交易等待与回调改善，与依赖消费者提前及整段周期减少相一致。

不可写：这两个页单独导致整段40.704157%收益；页B等待全部由页A阻塞；已经独立识别纯Bank而非row/调度/局部性效应；自然MoE/任意MLP/实际多用户已获同等收益；在线安装净收益已通过。

如需严格“两页独立因果效应”，还需另行批准配对反事实：保持其他活跃页布局不变，只移动目标页并用合法非活跃页置换保持双射，再记录明确阻塞者及消费者路径。现有日志不具备这份独立干预，本轮没有启动该实验。

## 文件入口

- EVIDENCE_CHAIN.json：机器可读结论、检查与边界。
- PAIR_OFFSET256.csv：主例的四条交易记录。
- PAIR_ALL_TRANSACTIONS.csv：两页前后全部64条交易，含offset0反例。
- PAGE_OPERATIONS.csv、DEPENDENCY_PROPAGATION.csv：完整页事件和消费者。
- SOURCE_MANIFEST.json、source_snapshot/：原始来源字节绑定与小型快照。
- ORIGINAL_EC_PAIR_STATUS.json：上一例eC缺少目标CA逐事务日志的明确记录。

原始来源：[受控合同报告](../qwen3_strategy_native_v1/evidence_v1/REPORT.md)、[图](../qwen3_strategy_native_v1/evidence_v1/graphs/coaccess_witness/ops.csv)、[依赖](../qwen3_strategy_native_v1/evidence_v1/graphs/coaccess_witness/deps.csv)、[RR事务](../qwen3_strategy_native_v1/evidence_v1/runs/coaccess_witness_rr/bank_requests.csv)、[CA事务](../qwen3_strategy_native_v1/evidence_v1/runs/coaccess_witness_coaccess/bank_requests.csv)。

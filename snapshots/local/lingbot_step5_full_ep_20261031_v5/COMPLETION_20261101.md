# 完整MoE/EP16两轮验收（2026-11-01核查）

结论：完整98869行MoE/EP16子图两轮有限通过，步骤5整体仍PARTIAL。目标GPU0、原混合BF16/FP32、host128GiB/HB8GiB保持；无新增GPU参考、完整模型或物理NPU运行。

## 已核实结果

- 每轮双CFG共98869行。3个边界（FFN输入、FFN输出、post-FFN norm）共607451136个BF16值的FP32容器元素逐位核对通过。主独立审计84741项通过，非84741个独立样本。
- 每轮7680次逻辑远端传输、6098063104B实际载荷、96880条水平PopNet。逻辑包按64KiB分段，因此不能把两个记录数当重复流量。
- 第二轮96880条水平消息全部应用前轮反馈；每轮995196条域服务顺序通过。两轮是同一已见example_4/layer0/step0的反馈重跑，不是独立留出或收敛证明。
- 每轮显式宏事件DAG21536节点/29200边，发送接收SHA与字节匹配、接收完成不早于发送完成、无环；每轮4项审计负对照通过。
- 每轮真实SRAM暂存读写各12900959488B，Bank服务100792808周期；两轮160项独立计数/分块/峰值检查通过。4MiB数组、64KiB暂存峰值；32B条带/8 Bank单共享端口为研究配置。未覆盖每MAC/每软件算子的全部Bank访问。
- 66条子进程退出记录全部0，控制器退出0；墙钟30118.86秒，约8小时22分。墙钟和缺项尚存的仿真宏周期均不是完整目标物理时延。

源完整FFN输入来自步骤4自主CPU全量结果，先核SHA；自由router重新计算，专家在真实owner端重新计算。实际dispatch/return、HB存取及SRAM读回完成后才释放消费者。原GPU结果只用于验收，没有用采集专家输出替代计算。但本次没有执行完整查询的TP attention，不能写成完整DiT层目标通过。

## 本地交付与独立复核

原compact包358成员/28899324B，SHA77ec3336fba02783598ea7ea0b53be38632dff31cfd25d7c500b5ef6e2e32621。该包4MiB文件上限遗漏了大型主审计JSON；远端回执原本存在，此次单独取回并核SHA，再生成补充包。旧包不改。

补充包329成员/26231127B，SHA c4d1ccda0f8c2fb6318113b49166e24efc88f37bc8530a897e5176d3f9d1bfe1。两包及各自全部成员SHA本地通过，成员有重叠，不相加称独立载荷总数。主审计原JSON的84741项已在本地核对全部passed。

本地重新从两轮原生事件重建DAG、配对7680次消息、核HB512MiB边界并独立复算Bank字节及周期，全部通过。没有把远端数值审计等同于本地重算完整GPU比较。

525项不可变数值/事件/CSV/代码快照索引覆盖192个大数值数组，4859633664B，原数组留113；不含原始控制台日志或归档本身。POSIX其他用户可读/目录可遍历检查通过，未跨账号登录。源原始过程日志也保留113，没有声称全部日志回传。

## 后续

完整TP attention/O及精确MoE检查点拼接已在../lingbot_step5_full_tp_20261101_v6/启动。全量新FFN输入必须先与本实验输入逐位一致，才允许消费本实验结果。该拼接验证功能同一性，不是连续统一全层时序；CPU/host/PCIe、全算子ISA/缓存/每MAC SRAM成本和策略收益仍未认证。

来源：review/各case原生EVENTS/SRAM_SUMMARY/bench/delay，complete_review/INDEPENDENT_AUDIT.json、DAG_AUDIT.json、SRAM_INDEPENDENT_AUDIT.json、FEEDBACK_AUDIT.json、COMPLETE_RAW_MANIFEST.json，以及LOCAL_COMPLETE_AUDIT.json、LOCAL_SUPPLEMENT_AUDIT.json。旧失败与主动停止保持不变。

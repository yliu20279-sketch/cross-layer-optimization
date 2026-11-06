# 步骤5第4项：联合lowering、原生回调及RR身份回归

2026-10-20，113隔离目录 `/mnt/sda1/h3240101068/selector_fp16_joint_native_20261020_v1`。

结果：`PASS_NATIVE_JOINT_RR_IDENTITY_SCOPED`。两模型各四旧请求作为一个块级图，分别进行直接RR与RR身份映射两次，合计4次真实原生运行；两对周期、完整DRAM/NoC事件流及原节点事件完全一致，独立逐笔日志检查通过。无三策略、新组或全模型性能结论。

## 协议、模型范围

先检查113任务与新增资产，未重复启动，未干预其他用户的长期进程。冻结protocol.json，随后在真实运行前记录implementation_amendment.json、构建manifest和decision_freeze.json，保存二进制及输入哈希。原tau17、选择器17文件、旧物化和失败结果不改，封存数据不读，无新采集。

本轮是新的浮点块级原生参考变体：复用实际Ramulator2与PopNet后端对象/库，完整提交全部有效字节事务，完整注入通信payload；不是旧“采样Ramulator+整op DeepStack floor/缩放NoC”运行口径。原生运行表示调用真实模拟器后端，不表示GPU或芯片实测。不能直接和旧W4/采样周期混比，也未认证旧动态NoC带宽模式或完整模型paging。计算时序仍为声明的项目解析模型，非硬件校准。

## 联合lowering与完成

Qwen3有100、Qwen1.5有104个WEIGHT_READ/LINEAR配对，仅允许WEIGHT_READ唯一消费者为相应LINEAR。联合域等待两节点所有域外父依赖，收缩图检查无环；down等操作不会越过其激活输入依赖。

保留原节点ID和外部依赖，内部整投影屏障显式细化为tile数据依赖，不声称原内部整op屏障时间完全不变。WEIGHT_READ完成记录在最终tile读门槛回调后，LINEAR完成记录在全部输出tile写回之后；没有把WEIGHT_READ改成零时长描述符，也没有重复读完整投影。读完成门槛可能保守等待该tile的激活读，不提前于最后实际读回调。

联合域全部读写共用原WEIGHT_READ ID的16事务信用池，跨tile单调token；保留原LINEAR ID的最终完成日志。不是原两个节点各发一池，也不是页级池。RR身份检查适用于该预先声明的联合执行语义，不是未改旧执行语义的身份回归。

## tile与SRAM

复用现有ScaleSim工具链及64×64 WS配置，新运行(1,64,64)、(1,64,60)、(1,64,1)三个tile画像，外存stall均0，按既定每阵列步2周期得到阵列服务均380周期。不是完整GEMM周期均分。

每K递增，FP32部分和跨K驻留，首K清零、后续K增加一次向量FP32 add，最终K才FP16转换；延迟采用既有16向量lane、add4/convert1和issue1规则。N=64/60续算add7周期、末次转换4周期；N=1分别4/1周期。LINEAR_SIGMOID最后增加冻结sigmoid向量服务，无GPTQ解包项。

每partition先扣除前轮私有工作区、通信payload、向量scratch、常量和控制预留，再由同一SRAM池预约tile，跨K复用，最终写回释放。该有限图的保守总账预留全部活动tile，因此原生的预约失败视为合同错误；通用背压/重试已由先前独立模块测试，本轮没有声称原生压力下触发了SRAM容量竞争。结束时全部池归零。

## DRAM与NoC

Ramulator前端接收成功才提交Operation.accept；拒绝不推进cursor/token/信用。原生256字节上限事务按4KiB边界和有效尾字节拆分，scheduler1ns与DRAM1.25ns tick保持分离。回调带联合域owner及token，先归还信用再推进阶段。

SEND完成源端操作数读取及staging写回后注入完整payload的PopNet packet，最后packet回调才完成SEND；RECV不重复跨partition读取源DRAM，等待SEND/NoC完成后写目标缓冲。没有仅凭注入时刻提前完成通信。静态4×4拓扑复用原命令，所有packet/事务完成后退出。

## 离线与原生结果

两模型整图先跑显式假回调模式：不向真实后端提交任何事务/packet，测试拒绝、反序回调、阶段完成和排空；这些不是原生性能参考，不计入4次RR。summary明确offline_mock=true，假后端周期不作性能解释。此前独立模块负例测试仍复用。

| 模型 | 直接RR周期 | 身份RR周期 | 每次DRAM事务/回调 | 每次NoC packet |
|---|---:|---:|---:|---:|
| Qwen3 | 2,740,803 | 2,740,803 | 2,420,362 / 2,420,362 | 270 |
| Qwen1.5 | 8,232,918 | 8,232,918 | 4,417,858 / 4,417,858 | 186 |

每次Qwen3读取309,511,292有效字节、写入1,000,760字节、37,120个tile；Qwen1.5分别564,044,316、1,016,432和67,840。有效字节不等于DRAM物理burst传输字节，尾部/窄row事务可能消耗完整burst，不把这些数字混同。

两对events.csv和nodes.csv SHA256分别完全相同。独立脚本逐笔解析每模型直接运行的完整事件流，再核对身份流hash：最大原域在途均16，所有issue/callback唯一配对、无越界/跨页事务；NoC packet唯一配对、原完成事件432/404项齐全、联合域完成不早于最终写、外部DAG消费者不提前。RR物理页置换另外从旧物化对象独立重建确认，router和工作区保址。

来源：identity_results.json、independent_validation.json、build_manifest.json、decision_freeze.json、tile_timing.json、两模型lowering/runtime_input_manifest.json及runs/*/{summary,nodes,events}。原始日志及二进制保留远端；本地证据包含源代码、输入、摘要、日志哈希与审计，完整大事件日志不重复回传。

## 结论与下一步

当前浮点块级参考变体的原生接入和两模型RR身份检查通过。它没有证明选择器在自然负载上的预测排序可靠，也没有Heat/CoAccess增量收益。

下一步可进入步骤5的旧开发组三策略有限排序检查，先冻结选择/页表和信息边界再跑参考；不能直接打开A/B新组或扩大矩阵。本轮已经用满4次RR，不追加运行。

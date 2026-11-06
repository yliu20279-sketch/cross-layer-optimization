# swe_qwen3统一工具链：16节点及通信时钟修订

原BF16、128 GiB host＋8 GiB HB、目标GPU0保持；本轮无新GPU、SWE/agent、gold或隐藏测试访问。这里的gold仅指已冻结的模型数值参考文件，不是SWE补丁答案。

## 已确认的实际结果

此前单活动NPU/HB的连续两层用例已完成156105条PopNet回放、CPU双结果和独立审计；113载荷本地SHA通过，包7608432 B，SHA256为7db3c9d1d1dc2329d0485796836247beab46b011b46e89469449815e4741c2b7。它是诊断拓扑的有限功能证据，不能用其周期认证规范目标时序。

已实际运行16 NPU＋16独立512 MiB Ramulator分区、规范16-router mesh＋gateway的原BF16专家gate投影。输入取R0002的CPU源路径真实Top8中每个expert_id mod16 owner首次出现的位置；16个唯一投影分别重复两轮，不是32个独立样本，也不是完整分布式层。完整16个原模型分片重新读取校SHA，共61066575648 B；host文件映射及实际参数读取、PCIe/gateway、XY NoC、HB读回和CPU回传都已接通。

首版16节点数值/载荷通过，但随后发现时钟单位错误；其功能证据保留，时序不晋级。修订版swe_qwen3_legosim_16_service_20261030_v2已经完成两轮：每轮16输出/12288 BF16元素、1600笔HB请求、816水平NoC记录、4016 HB RPC记录、816 PCIe记录，全部5648条transport记录分域保留；第二轮全部816条NoC请求实际消费反馈。289项XY next-hop逐项通过。

修订版每轮11296条时钟观测、逐通信对的ready边界通过；381载荷本地SHA及独立功能/时钟审查通过。包4631222 B，SHA256为d9db764a66f51b47d13252f28d7150f2d33292a407d8d97c9501e81ced9acba7。完整61GB模型保留113，本地校验的是审查包与其核验元数据，没有再次本地遍历模型文件。

## 两项单位错误和边界修复

Sniper接口把SubsecondTime除以global domain周期后输出tick；该domain由当前2.5 GHz配置初始化，因此tick为0.4 ns。旧CPU进程clock_rate=1将这些tick当作1 ns。修订为CPU clock_rate=2.5，NPU、gateway、NoC仍为1。

Ramulator2Wrapper.run返回DRAM周期数；运行时tCK为1.25 ns。旧服务器cycle_scale=1.0没有作该换算，修订为1.25。原BF16数据及数值参考不变。

全局服务按1 ns向上量化ready，响应向接收端tick向上取整；例如385 ns在CPU端应回963 tick，而不是截断为962 tick。独立边界测试及0—10000 ns取整检查通过；不会将截断后的提前唤醒当作完成。

实际时钟CSV同时含CPU和gateway观测。PCIe每个通信对恰有一个2.5和一个1；其他域为两个1。最初审计错误要求CPU链路的gateway也为2.5，已以独立修订脚本更正；原失败和原冻结文件均保留，BF16容差、输出及计数标准未改。

源码与SHA见BINDING.json：Sniper common/core/syscall_model.cc、common/system/dvfs_manager.cc；Ramulator2-Chiplet/ramulator2_wrapper.cpp与main.cpp。实际运行证据见../swe_qwen3_legosim_16_service_20261030_v2/review/及LOCAL_CLOCK_AUDIT.json。

## 完整连续层的当前推进

完整服务driver已实现：N0执行前半层、attention/KV/router/合并，专家矩阵按expert_id mod16发送到对应NPU；所有原模型参数经真实Sniper host从原checkpoint映射区供给。CPU源参考中的参数不作为设备权重字节注入。当前是阻塞、经host中转的功能基线，不含Sem-MoE/HiBand调度优化或并行收益主张。

首个完整候选因遗漏WORKER_FREEZE清单在计算前停止；第二个候选已通过prefill层0的14阶段，但因发现上述单位错误主动停止，不能晋级时序。失败、停止原因和数值证据分别保留在16_layers_v1/v2目录。

时钟修订后的swe_qwen3_legosim_16_layers_20261030_v3于22:23启动，22:36完成第一轮完整prefill两层和cached decode两层。56阶段对冻结CPU源参考逐字节一致，12输出/KV与CPU双回传通过；759次矩阵、450次远端专家矩阵、61次host参数fetch已实际完成并逐RPC核对，全部15个远端owner的权重/input/output SHA及last-reader通过。160载荷本地SHA与433510条时钟观测通过；phase1包10929626 B，SHA256为d4d21bd28c44e0851643b3bfa017b31510a0dcbdd01895b05337490938a88680。该包遗漏FREEZE索引，已单独补取并按冻结值核对，原包未改；实际数值断言没有放宽。

第一轮水平PopNet共28316条记录，截至22:54已生成18741条delay；完整第二轮尚待执行。独立后台只读审计/归档器已启动，不重复数值运行；最终应检查INDEPENDENT_AUDIT.json、CLOCK_AUDIT.json、COMPLETE_DELIVERY.json或COLLECTOR_FAILURE.txt。当前通过范围仍是完整16节点phase1功能/数据依赖，不是完整反馈或全目标时序。

## 23:18运行状态补充

第二轮完整prefill/decode两层的56阶段、12输出/KV、CPU双回传以及每轮759矩阵/450远端/61fetch均已通过前置门控。第一轮全部28316条水平NoC回放通过，delay SHA为5ef86fc804765a3659db15ac2625e36929f1a7a98c16d879340c6c8522710323；目前第二轮PopNet回放正在运行，最终完整独立审计与归档尚未完成。两轮是同源输入的反馈重跑，不是两个独立样本，也不认定反馈已经收敛。

## 1—7步仍为PARTIAL

统一入口、有限16节点真实载荷和通信时钟绑定已有实跑证据；完整分布式层仍在运行。即使该用例通过，BF16 codec/软件特殊函数的完整CPU或NPU lowering成本、实际SRAM驻留/8 Bank仲裁及完整显式数据DAG仍需补齐。当前通用FP32 vector/reduce代理不能当作BF16原生阵列吞吐；不可变缓冲保留到结束也不证明动态释放/异步重排正确。LPDDR5服务仍是研究代理，HB固定电气延迟未知，不补造物理参数。

保留原GPU的GEMM及softmax FP32差异；原prefill输出4249元素、路由10槽位差异不撤销。无物理NPU或HiBand/Sem-MoE净收益结论。

# 步骤5 CPU服务双轮有限验收

2026-11-01。状态PASS_LIMITED，步骤5整体仍PARTIAL。

真实Sniper CPU通过网关接收NPU从HB/SRAM读出的操作数，执行原精度兼容FDA16软件核，再将FP32/BF16结果送回NPU，后者实际写入HB/SRAM并消费。覆盖单查询K、V和带已有FP32累加器的O末分片；每轮2304个输出，原始FP32对软件/既有累加器参考逐位一致，BF16对原GPU Golden逐位一致。没有新增GPU运行。

两轮各516项时钟观测、217项域服务记录、41条水平PopNet消息；第二轮全部应用第一轮反馈。10个子进程和外层返回0，外层墙钟186.02秒。独立本地重算CPU 2.5GHz与网关1GHz时钟配对、完成先于消费、原始二进制及反馈均通过，见LOCAL_AUDIT.json及review/INDEPENDENT_AUDIT.json。

主包94载荷，SHA256为7b49626aaf123e4b87ef072aca108c07bd0114f0357afa0160265b160f6274b3。主包原先排除了run目录，补取clock_evidence.tar.gz，SHA256为dbcab3d62cde49ec413bacff69252d0b68ace2012fa7eb9c2f0617b806c1938b；补包包含原始时钟/域服务/反馈CSV，均已本地重算。不能仅凭主包声称时钟原始证据齐全。

该探针仅一个活动NPU和512MiB HB，研究配置仍为host128/HB8、目标GPU0、混合BF16/FP32。它补齐了有限CPU回调因果链，不代表16NPU全层CPU成本接入。初始数据放置、CPU缓存一致性/维护、完整PCIe/算子/SRAM逐MAC成本仍未认证，不能外推性能收益。完整TP仍在独立后台运行。

相关CPU独立成本样本见../lingbot_step5_cpu_fda_20261101_v8/REPORT.md；v7导入失败现场保留。验收门槛未修改。

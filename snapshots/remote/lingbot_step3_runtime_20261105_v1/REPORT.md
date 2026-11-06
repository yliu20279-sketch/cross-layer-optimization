# 双 CFG 有界成本探针验收（2026-11-05）

状态 PASS_LIMITED_DUAL_CFG_K_SERVICE，实际回执顺序复核 PASS_LIMITED_RUNTIME_RECEIPT_ORDER。本地审阅包110载荷SHA逐项通过。步骤3的小路径执行与时序门控有限通过，完整单层成本仍PARTIAL。

真实输入为example_4 step0/layer0/query0/head0的K投影，每支M1/K2048/N128。分别从原block输入重算norm/modulation，与各分支保存的GPU输入逐位核对；使用原BF16权重。cond及uncond各128 FP32输出对软件参考、128 BF16输出对原GPU K投影逐位通过。实际Sniper、NPU/HB和Ramulator执行，两支沿用服务框架的两个round槽位，10子进程均0，运行约68秒。非独立视频留出。

实现了网关内确定性PCIe服务模型，沿用V3.6 Gen5×16、55.04GB/s、256B分段、250ns固定与20ns IOMMU延迟。选用串行queue0，逐段向上取整到1ns；请求528384B/2064段、返回768B/3段。模型完成时刻推进活动网关时钟并约束后续发送。轮询完成边界取实际接收观察，没有细化CPU轮询指令开销、队列争用或PCIe链路协议。

CPU执行FDA16软件核后，对实际结果缓冲执行软件LRU逐出，并调用已有Sniper目录写回完成屏障。原始MAINT_DRAIN中cond发出78项写回、uncond65项，均pending0；实际等待分别82.333110ns、82.079408ns。写回确认在屏障返回后发送。CPU/写回门控时间使用保守接收端观察，另独立核对原始CPU fs时刻和网关DMA时刻。

消费者在四项回执齐全后才提交并读回HB结果。cond释放14016567ns，uncond13951732ns。独立检查消费者不早于CPU返回、DMA完成、写回确认和最后一次NoC接收；每支四项实际回执延迟负对照通过。负对照为捕获实际回执的门控重放，未重跑延迟硬件仿真。首次负对照延迟1000ns不足以超过更晚回执，触发审计断言；修正为超过原最晚完成1000ns，原脚本保留。

NoC第一支使用统一域服务，第二支应用前支同形状PopNet反馈。两支各有PopNet回放，未建立每一分支独立反馈收敛。当前只一个活动NPU/HB和CPU0，未接入完整层、TP16/EP16全部成本。正式PK与CA消融均未执行。

可复核入口为INDEPENDENT_AUDIT.json、RUNTIME_RECEIPT_AUDIT.json、INPUT_BINDING.json、IMPLEMENTATION.json、FINAL_DELIVERY.json和LOCAL_PACKAGE_AUDIT.json。原始cpu.log、DMA回执、clock/domain/NoC CSV、构建源码与二进制在runtime_review.tar.gz及113原实验目录。复跑需新建隔离目录，在生成数据后使用prepare.py和run.py；run.py内置600秒进程组上限，外部另750秒上限。setup_corrected.py产生网关后仍需应用实际归档gateway.cpp中的修订，复跑以包内最终源码为准。

所有旧目录和既有结果保留。源生成脚本第一次有字符串换行错误，失败记录保留；最终构建与运行代码收录在审阅包。全精度配置保持混合BF16/FP32，目标GPU0。

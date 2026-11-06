# 步骤5续作：原精度CPU软件FDA16成本小探针

状态PASS_LIMITED，仅此小片段通过；步骤5整体仍PARTIAL。全量TP attention/O仍在113后台运行，本探针未重启或修改它。

## 实际执行与数值

使用同一真实cond/query0：K/V为head0的两个M1/N128/K2048投影；O为head15的M1/N2048/K128保序累加器更新。K/V输入由原block输入重新做CPU norm/modulation产生并与原GPU输入逐位核对，权重取原checkpoint切片；O初始FP32累加器和BF16 core取此前已通过的16节点原生事件执行结果，保留真实非零状态。

复用步骤4固定的FDA16整数对齐语义，独立生成标量C，按Nehalem/SSE可执行基线编译，关闭AVX/FMA及fast-math，无OpenMP。模型持久数据保持BF16、累加器FP32，内部整数位操作不是FP64模型运算。没有新增GPU或FP16替换。

先在独立native_data目录做软件数值检查，再在不同sniper_data目录真实运行Sniper，防止把前者的PASS文件当成后者回执。Sniper退出0并产生独立功能回执：2304个FP32累加器值对既有软件/原生载荷参考逐位一致；2304个BF16输出对原GPU逐位一致。FP32参考不是原GPU原始累加器。

## 成本记录与口径

4核gainestown派生CPU/2.5GHz、原host128 overlay、一个活动线程；L1/L2/L3与恒定DRAM配置沿用项目CPU overlay，非物理校准。SimRoiStart/End之间执行真实BF16 decode、整数软件FDA、bias/encode。数据文件读取、缓冲分配和初始placement在ROI之外；未调用CLFLUSH或软件cache逐出，不认证缓存维护时序。

| 内核 | decode/core elapsed ms | FDA/core elapsed ms | encode及bias/core elapsed ms |
|---|---:|---:|---:|
| K head0 | 0.8010740 | 4.0723652 | 0.0004356 |
| V head0 | 0.8011384 | 4.0282532 | 0.0004116 |
| O head15 carry | 0.8015808 | 3.4847232 | 0.0105960 |

全局ROI为14.0191184ms模拟时间、35047796周期、70404194条指令；单核elapsed统计差为14.0012964ms。SQLite barrier.global_time与2.5GHz的400000fs/周期及sim.out相互核对通过。两种口径不同，不能直接相等；日志的全程序CYCLE46120179也不等于ROI周期。首次本地汇总的口径相等假设被数据拒绝，原日志不改，现明确分列。

上述9段来自独立marker区间，涵盖所列实现的控制与内存操作，不代表纯硬件FMA成本。它们不能按M1结果直接外推全层，也尚未替换全量运行的通用向量代理；完整CPU回调、host/PCIe、各形状、缓存状态及完整层统一完成时间仍待接入和验收。

## 失败保留与交付

v7在准备阶段缺少sfu_cpu导入路径，未编译或进入Sniper；目录、日志及失败包保留。v8仅修复隔离导入路径，数学和预算未改。prepare/native/Sniper分别180/30/240秒上限，实际Sniper墙钟约87.39秒；超时按本任务进程组清理，无自动重试。未修改共享Sniper或步骤4源缓存。

80载荷、3949034B归档，SHA b54d37a860cf5c2d622a5da146a417ec042eb3d34e1998794eaff92757540cd8。外包及所有成员本地SHA通过；本地重新核全部二进制位值，并从原SQLite重算9段计时和全局ROI。原输入/结果、生成C、编译指令、sim.cfg/sim.out/SQLite、日志和Apache许可证已归档。

来源：review/INPUT_BINDING.json、portable.c、kernel.cpp、COMMAND.json、sniper/sim.stats.sqlite3、sniper/sim.out、INDEPENDENT_AUDIT.json及LOCAL_AUDIT.json。FDA方法源码沿用../lingbot_step4_bitexact_20261029_v4/tc_emulator_simd.py及其固定upstream/许可证，不把软件语义复现称为目标BF16阵列或物理性能通过。

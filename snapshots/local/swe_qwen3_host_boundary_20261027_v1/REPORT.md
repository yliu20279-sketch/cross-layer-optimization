# swe_qwen3：host转换、展开缓冲与链路耦合

日期：2026-10-27。状态：PASS_LIMITED_HOST_CODEC_PCIE_NATIVE_ROUTER_COUPLING。原BF16、host128 GiB＋HB8 GiB overlay不变；这是router投影子链的显式模拟代理，非完整router/层/模型或物理时延认证。

## 已补齐的子合同

1. 实际NPUSim BF16 codec编译为标量x86_64内核，在项目既有Sniper上分别运行decode、encode ROI，各一次且退出0。264192个BF16元素扩展后位型正确，128个FP32输出回写BF16与原GPU一致。Sniper实际解析为4核、2.5GHz、32/32KiB L1、256KiB L2、8MiB L3；应用单线程。不是113墙钟换算。
2. 128GiB host内完整只读BF16权重保留；局部FP32展开缓冲峰值1056768 B（约1.008MiB）。运行时16GiB、IO1GiB仍是预留预算，非整模型实测峰值。两个64KiB DMA窗口租约指向这块已固定的展开缓冲，不另建bounce副本；当前串行路径窗口峰值65536 B。DMA固定页、分配器及缓存维护的CPU成本尚未模拟，不能当已免费支持的通用系统。
3. PCIe配置代理55.04GB/s/方向、每包最多256 B、单向传播250ns、每描述符一次20ns IOMMU命中；4队列×16credits，64KiB描述符分块。方向内串行化、双向serializer独立；credit/窗口一直持有到endpoint最终完成。自然样例只串行使用少量资源，64-credit饱和由合成负对照覆盖，不伪称真实并发吞吐验证。
4. host DMA读/写增加独立共享DRAM serializer：12.8GB/s、每chunk60ns。这是明确的实验代理，来自CPU overlay的constant-DRAM假设，不是V3.6规范已给定或已测host带宽。CPU与DMA在本串行样例不重叠，未验证共享控制器真实竞争。
5. 转换完成→host DMA源读→PCIe→原生HB写提交→计算的依赖已接通；返回为HB读完成→D2H→host DRAM写完成→encode。原生NPUSim/Ramulator在新时间线上重新执行，不是平移旧250447周期日志。

## CPU统计与计时规则

| Sniper ROI | 完整ROI时间 | nonidle | idle |
|---|---:|---:|---:|
| decode | 856075.2 ns | 800839.2 ns | 55236 ns |
| encode | 101871.2 ns | 2202 ns | 99669.2 ns |

来源：attempt1/SNIPER_RAW_METRICS.json及decode_sim/encode_sim的sim.out、sim.cfg、sim.stats.sqlite3。主耦合结果保留完整ROI，包括上述idle，因此不能将其称纯codec指令成本。周期先按Sniper原生fs读取，到NPU全局1ns门控时仅向上取整一次，没有把CPU周期直接当ns。

STATUS中nonidle_only_sensitivity_ns字段只是主结果减去idle的算术视图，**不是另一次模拟**。减去idle可能改变DRAM刷新、相位与取整，不能作为另一个合法目标时延或收益数据。独立审计已明确此范围，正式结论排除该字段，不据它报告性能。见CPU_SERVICE_ACCOUNTING.json及coupled_attempt2/INDEPENDENT_AUDIT.json。

## 实际耦合与审计结果

采用coupled_attempt2，第一版coupled_attempt1保留为少算host DMA DRAM endpoint服务的历史结果，不作本轮最终时序依据。修订前冻结HOST_DMA_AMENDMENT/COUPLED_FREEZE_v2，原输入/数值门槛不变。

| 指标 | 最终结果 |
|---|---:|
| 原生事件 | 16689 |
| 32B DRAM事务 | 66336 |
| DMA描述符/载荷包 | 18 / 4130 |
| H2D / D2H载荷 | 1056768 / 512 B |
| HB读取 / 写入 | 1065472 / 1057280 B |
| 展开host缓冲峰值 / 固定窗口峰值 | 1056768 / 65536 B |
| SRAM峰值 / CH0地址保留峰值 | 17408 / 1057280 B |
| 主配置代理完成时间 | 1462074 ns，约1.462 ms |

新计算的FP32输出逐字节等于先前被Sniper encode计时的输入，因此没有把不匹配的数据分支成本贴到新输出上；回写BF16 bits也逐字节等于原GPU。结果为同一原checkpoint的首decode router GEMM，不含softmax、Top8或其他层。

独立audit_coupled.py逐事件检查：早于消费者的producer完成、HB全部地址范围与32B sector计数、SRAM分配释放、256B包序与带宽/传播、每描述符IOMMU、credit不重叠、窗口last-consumer、host DMA读写服务、host128容量预算、fs→ns门控、真实输出位型。7项边界控制（第三窗口、pending释放、last-consumer、提前DMA完成、65th未完成credit、双向独立serializer、上传前HB消费者）及3项原生依赖/容量控制通过。

原始证据：coupled_attempt2/STATUS.json、INDEPENDENT_AUDIT.json、events.jsonl.gz、sram.jsonl.gz、LINK_*、HOST_DMA_MEMORY.json、HOST_ARENA.json、CLOCK_AND_UPLOAD.json、new_router_*.npy。CPU证据在attempt1；coupled_attempt1缺项和所有冻结/源码均保留。整体累计本线NPUSim原生片段3次（原片段1＋本轮两次），Sniper ROI2次；物理NPU0。没有新GPU推理、agent或新留出正文访问。

## 仍然不能声称的内容

完整BF16目标时序仍未认证：DMA描述符CPU准备/轮询、内存分配/缓存维护、物理gateway/HB固定传播缺依据；CPU gainestown-derived及constant DRAM是代理，未作物理校准。本轮没有CPU gateway InterChiplet全在线协同、NoC、pager、多NPU、完整层/两层或Sem-MoE/HiBand收益。固定窗口零拷贝假设也未成为操作系统DMA实现认证。

下一步可在已完成门控框架上增加softmax/Top8或一个专家子链的独立功能验证；完整时序则须先固定DMA控制软件与缓存维护协议，取得对应Sniper/设备代理依据，不能为了“全链PASS”给缺项填0。现有SWE结果仍单独验收，不阻塞本线。

## 来源与交付

配置：../whisper_operator_inventory/target_architecture_v3_6/target_architecture_v3_6.yaml、pcie_dma_model.json（含20ns IOMMU）、clock_domain_mapping.json；host容量../mini_swe_storage_audit_20261026_v1/STORAGE_CONFIG.json；CPU overlay及PROTOCOL.json明确区分规范字段和实验假设。

codec源码：../olmoearth_v3_6_integration_20261025_v1/source/NPUSim/npusim_tensor_codec.h；原生桥与上阶段见../swe_qwen3_native_router_fragment_20261027_v1/REPORT.md。权重/fixture SHA及CPU源码绑定见attempt1/SOURCE_BINDING.json、CPU_RUNS.json和上阶段PRE_RUN_BINDING。

交付文件与包SHA见DELIVERY.json、FILE_MANIFEST.json；本地验收见LOCAL_DELIVERY_VERIFICATION.json。文件完整性、功能及代理时序分别判定。

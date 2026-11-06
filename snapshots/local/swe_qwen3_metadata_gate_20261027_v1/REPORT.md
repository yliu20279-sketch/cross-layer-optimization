# swe_qwen3：CPU路由metadata完成门控

日期：2026-10-27。结论：PASS_LIMITED_CPU_ROUTE_METADATA_HB_DISPATCH_RELEASE。已接通CPU整批完成、两平面搬移/HB提交、SRAM可见性和dispatch描述符释放；不是token已到达专家、完整payload dispatch或整模型认证。原BF16、host128GiB＋HB8GiB overlay不变，softmax FP32差异保留。

## 实际数据流

用上阶段固定759行BF16 logits重新执行独立SourceCudaRoute128，产生本轮metadata；没有将记录ID传入生产函数。完成时间引用完全相同759行、冻结内核与CPU配置的已完成Sniper ROI：3715344800000fs，转全局1ns后向上取整为3715345ns。没有新Sniper运行，也没有把批次时间除成逐token成本；不是本轮在线CPU/InterChiplet联合模拟。

wire ABI为两个直接DMA平面：int64 IDs48576 B、BF16 weight bits12144 B，合计60720 B；CPU数组不重新交织打包。target模型使用固定数组窗口租约，Python为模拟传输/日志生成的副本不是目标DMA驱动实现。没有认证操作系统pin、cache维护或真实零拷贝驱动。

N0/CH0布局：IDs byte0，weights byte48576；地址保留60736 B（尾部对齐32B）。两个H2D描述符共238个≤256B载荷包。复用上阶段55.04GB/s/方向、250ns传播、20ns/descriptor IOMMU，以及明确实验性的12.8GB/s/60ns host DMA DRAM代理。原生Ramulator写回调完成后才发布平面；只有两平面均完成才允许HB读取metadata。

HB读回调、SRAM fill及metadata读取服务完成后，门控解析真实搬移的int64 ID和BF16 weight位型，释放6072条固定32B控制描述符。字段保留global row、phase内local token、slot、expert、owner=e mod16、origin=local token mod16、BF16 weight bits、逻辑activation offset及epoch tag。origin在每个源phase重置，未按合并批次global row错误编号。

描述符总194304 B，是host功能控制队列payload；不冒充NoC消息。input_ref=row×4096仅是合并activation张量的逻辑字节偏移，**不是已绑定HB物理地址**。真正token dispatch还须activation生产/驻留/last-reader、源/目的队列、NoC接收和专家权重就绪等门控，本轮未执行这些阶段。

## 已核对的先后关系

| 观察点 | 当前固定批次的代理时间 |
|---|---:|
| CPU route完成门控（ROI时间只换算一次） | 3715345 ns |
| IDs和weights全部HB提交完成 | 3730203 ns |
| HB读回、SRAM fill/metadata读取完成 | 3739936 ns |
| dispatch描述符允许释放 | ≥3739936 ns |

来源：attempt1/GATE_EVENTS.json、UPLOADS.json、CLOCKS.json、INDEPENDENT_AUDIT.json。最后一行是eligible/release门控，不是descriptor构建CPU执行完毕的已计费时间；解析/构建的目标CPU成本仍为null。没有将零时长调度注记当作免费硬件执行。上述数值不能用于完整延迟或策略收益比较。

数据位型核对759×8=6072个ID/slot/BF16 weight全部保留，并与上阶段真实GPU路由期望一致。参考ID文件只在生产和释放结束后用于验收，不给生产函数或gate补写ID。新生产的softmax FP32中间值沿上阶段实现，原7阶段不逐位一致、最大差1.4901161193847656e-7继续记失败，不以本轮metadata传输通过覆盖。

## 审计与负对照

独立audit_gate.py重读所有原生事件和payload，核对CPU完成→host源读→PCIe→HB写提交→HB读/SRAM→释放的依赖、32B sectors、HB偏移、fs→ns换算、窗口last-consumer、759行source request/phase/layer映射及32B descriptor ABI。实际结果：

- 8个原生事件，HB写/读各60720 B，3796个32B事务（物理121472 B，尾部按32B服务）。
- metadata SRAM峰值60720 B，N0/CH0 metadata地址保留60736 B，均在4MiB SRAM/512MiB CH0内；不代表整层权重/KV峰值认证。
- 6072条descriptor、16个owner分区assignment守恒，源slot和weight位型不变；这是映射/控制队列，非16NPU执行。
- host显式数组与descriptor载荷合计837936 B，纳入原1GiB IO预算；不是含Python调试对象/allocator/stack的实测host峰值，128GiB完整模型容量与runtime预算不改。

13项门控负对照均拒绝：CPU提前发布、CPU完成前DMA、错误epoch、两平面分别的“包到达但HB未提交”、两平面分别重复回调、仅ID平面完成、SRAM读取前dispatch、SRAM读仍pending、内容损坏、dispatch最后消费者前释放SRAM、重复dispatch。原生桥3项SRAM越界/提前消费/缺失依赖控制也保留。

首版独立审计错误地要求启动负对照的4B缓冲也等到dispatch后释放，因而失败；原版audit_gate_initial.py及AUDIT_AMENDMENT保留。修订仅将启动cycle0的injected_early_consumer单独分类，metadata_SRAM仍严格要求最后消费者完成后释放，未改冻结执行器、未重跑原生片段。

## 边界与后续

此为固定epoch/批次、整批门控；没有证明多session异步、乱序RPC、epoch复用或真实网络故障恢复。未来批次必须创建新的epoch和完整上下文绑定，不得复用当前固定batch标签。

本轮新增原生metadata片段1次，本线NPUSim片段累计4、Sniper ROI仍3，物理NPU0；无新GPU、agent、SWE任务或新留出访问。SWE修复成功率没有作为门槛。

下一阶段应先绑定activation真实驻留/last-reader与NoC源/目的接收，再允许payload dispatch；本报告仅准入metadata依赖，不准入expert到达/计算、分页或Sem-MoE/HiBand收益。CPU控制解析/descriptor准备、cache维护和物理gateway传播仍未校准，softmax FP32差异仍独立处理。

## 来源与交付

协议/实现：PROTOCOL.json、FREEZE.json、metadata_gate.py、run_gate.py。原始日志、转移payload、32B descriptors、context、13负对照和独立审计均在attempt1。

父阶段：../swe_qwen3_softmax_top8_20261027_v1/REPORT.md与TARGET_FUNCTIONAL_CONTRACT.md；../swe_qwen3_host_boundary_20261027_v1/boundary_service_v2.py/REPORT.md；原生桥../olmoearth_v3_6_integration_20261025_v1/native_bridge.cpp/run_integrated.py。SOURCE_VERIFICATION.json核对新冻结及父阶段CPU路由/输入/原生桥字节身份未变。

DELIVERY.json、FILE_MANIFEST.json和LOCAL_DELIVERY_VERIFICATION.json记录封包与本地SHA。功能、代理门控、字节完整性、物理性能分别判定。

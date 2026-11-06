# 步骤 7：守恒时间归因

状态：代表层 full-trace 配对归因完成；完整 48 层端到端归因尚未测量。

## 方法

对层 0、8、16、24、32、40、47 分别运行 full transaction normal 与 owner-shadow oracle。使用 oracle 运行的关键路径拆分 Compute、NoC、DRAM、Paging DMA、Sync/Other；严格跨请求 Bank 项仅定义为：

`T_normal - T_owner_shadow`

所以：

`T_normal = oracle关键路径组成 + strict cross-request Bank exposed`

该方法不会把普通 DRAM service、同请求等待、row miss 或通用控制器队列误算为严格 Bank Conflict。

## 结果

7 个代表层的 normal 与 oracle 总周期完全相同，因此 strict cross-request Bank exposed 均为 0 cycles。normal 中累计严格等待仍然非零，范围为 1,650–140,170 ticks，说明冲突存在但未暴露在这些测量的端到端关键路径上。

采用最近代表层权重 `{0:5, 8:8, 16:8, 24:8, 32:8, 40:7, 47:4}` 得到 48 层外推：

- 总周期：456,507,114；
- Compute：111,395,240；
- NoC：42,339；
- DRAM service 与非跨请求 memory wait：46,234,946；
- Paging DMA：18,168,476；
- Sync/Other：280,666,113；
- Strict cross-request Bank exposed：0；
- 守恒误差：0。

该 48 层结果是分层外推，不是完整模型端到端实测。不能用它代替最终现象图中的正式全图柱状数据。

## 当前含义

full trace 修正后，没有证据支持 Bank Conflict 已成为主要端到端瓶颈。此前 4 KiB 采样下的 0.0699% 不再作为正式数字。

要完成完整步骤 7，仍需将 cycle-by-cycle memory driver 改为事件驱动或等价加速实现，并用代表层 full trace 验证后运行完整 48 层 normal/oracle 配对。

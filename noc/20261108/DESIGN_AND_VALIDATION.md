# 实现与验证索引

## 固定目标配置

- 16 个 NPU、16 个真实 Ramulator2 分区，总 DRAM 32 GiB；Qwen 切片采用 TP16+EP16/PP1。
- NPU/NoC 周期 1 ns，DRAM tCK 1.25 ns；转换只应用一次。
- 每节点 SRAM 4 MiB，256 B/周期共享逻辑服务口；接收匹配表占其中 128 KiB，不额外赠送容量。
- 单口优先级：NPU > 源 NI > 协议/接收 NI。NI 收发与计算不能同时免费使用同一个服务口。
- 3 个 VC，控制使用 VC0，数据使用 VC1/2；32 B/flit，有限源缓冲 1025 flit，控制 inbox 深度 8。
- 9 个 CS 位于 4×4 节点阵列各 2×2 单元中心，物理接入角依次 NW/NE/SW/SE。
- CS 配置为 12 bit：每个输出 2-bit SEL + 1-bit EN；禁止同端口回送及一个输入被多个输出复用。节点 TX/RX 选择值采用 16+全局 CS 编号。
- CS 参数 `2 1 1 3 1`：缓冲深度、链段、CS 延迟、信用返还、NI 服务周期；以对应代码和配置解析为准。
- 垂直 HB 服务按 128 B/5 周期序列化；未指定的固定电气传播延迟保留为空，没有臆造数值。

这些是当前受测模型的参数，不是工艺实现签核。

## 代码映射

| 内容 | 主要入口（snapshots 下） |
| --- | --- |
| CS / NI 数据通路与流控 | `noc_crosslayer_validation_20261108/noc/adapter/changes/aux_bridge.*`、`receive_contract.*` |
| 真实配置包、冻结/排空/提交 | 同目录 `dynamic_control.*`、`wire_protocol.*` |
| 真实接收就绪通知 | 同目录 `receive_ready.*` |
| 计算、端口、DRAM 因果约束 | 同目录 `program_fences.*`；`npu/causal_trace.h`、`ring_local.h` |
| 完成反馈和闭合判据 | `noc_crosslayer_validation_20261108/core/includes/net_delay.h`、`core/srcs/` |
| DRAM 全局时间与实际服务 | `ramulator_wallclock_20261107/ramulator2_wrapper.*`、`dram_func.*` |
| DRAM 请求编号 | `noc_crosslayer_validation_20261108/npu/reference_core/dram_request_id.h` |
| 短链原生程序与独立审计 | `noc_short_validation_20261108/short_chain.cpp`、`audit_chain_retry1.py`、`finalize_chain.py` |

## 本轮修复内容

1. 接收改为有限的非阻塞 posted receive，并使用真正占用 NoC 的接收就绪通知，避免发送/接收之间循环等待。
2. 显式核对源缓冲、共享 SRAM 服务、接收地址生命周期与消费者依赖，不将接收完成视作免费标志。
3. 固定同周期的 wire/credit 到达与 router 服务顺序，避免事件插入次序改变物理结果；移除旧源准入的重复服务。
4. HB RPC 从通用 8 B/周期假设修正为目标的 128 B/5 周期序列化。
5. 在原生实际传输处记录 DRAM 请求，并在因果求解中调用同配置 Ramulator，替代上一轮陈旧 DDR 间隔造成的反馈偏移。
6. 保持 64-bit DRAM 请求格式，将序号扩展到 33 bit；低于旧 20-bit 边界的编号完全兼容。新增边界、逆映射及真实存取检查。

## 验收依据

`tools/verify_release.py` 核对本次发布的字节、来源清单、Python 语法和八项总回执引用。此检查不替代原始大日志重放。

Qwen 首块 CS 与连续两块 Mesh 的最终两轮，原生请求、共享端口服务和 DRAM 完成不再应用临时数值指导；消息完成反馈严格相同。独立原 NoC 重放与真实 DRAM 重放通过。首次首块所涉 641,908 条 DRAM 请求、两块所涉 1,279,520 条请求均实际核验。

短链的绝对/相对反馈各 4 轮闭合。16 份关键网络输出在两种求解方式之间字节相同，36 份原始输入不变。它验证 Mesh→配置后 CS→Mesh 的计算/访存/通信依赖链，不是用短链替代完整 Qwen 性能结果。

组件组合测试使用的 `noc_ready_reconfigure_20261108/dynamic_control.cpp` 只修正诊断探针：真实 SRAM 查询可能推迟首条数据准入，因此必须等实际 accepted>0 后再注入重复 ARM。该探针测试二进制 SHA 与生产二进制不同，两者在回执中分别记录，不能混用。

两次短链历史审计失败由读/写发起时刻误判和汇总文件名错误导致。初始审计、修正审计及最终汇总代码均保留；最终结果以 `accepted_chain_validation.json` 为准，不能直接运行旧审计并覆盖已有结果。

## 尚不支持的结论

无全输入形式死锁自由证明、无全模型数值验收、无完整动态 HiBand 或完整优化策略性能对照、无工艺级 PPA。性能实验需要在统一应用与统一物理预算下另外完成，不由连接覆盖数量推出性能改善。

# CA–NoC 小规模正确性实验 · 2026-11-08

## 结论

24 项正向组合、6 项实际后端非法请求拒绝检查通过；独立原始证据审计通过。它扩展了此前两条传输的接口探针，仍是串行、有界正确性验证，不是完整应用或性能实验。

保持 16 个 DRAM 分区、每分区 2 GiB 的目标容量配置，实际 DRAM 事务为 32 B，NPU 使用当前目标配置。只有节点 0 和 5 在这些诊断用例中收发/计算；不将两个活动节点称作全部 16 节点并发覆盖。

## 正向矩阵

| 维度 | 固定测试值 |
| --- | --- |
| 消息载荷 | 32 B、2048 B、32768 B |
| 确定性输入种子 | 7、19 |
| 页映射 | 原映射、原 CA 入口实际交换两页 |
| 网络 | Mesh、静态 CS0 NW→SE |
| 用例总数 | 3×2×2×2 = 24 |

每项均在全新的 CA/NoC 状态中执行：实际写入 80 KiB 测试权重，按用例安装映射，读取当前物理帧，经真实 NoC 完成反馈后写入目的 HB，再由原生 NPU FP32 向量加法消费。

这些是人工构造的确定性诊断载荷，不是 Qwen profiling 或自然应用。页交换是固定合法激励，未运行学习得到的 CA 优化策略。

32 KiB 用例实际产生 1025 个 flit（含头），覆盖当前接口的单包容量上界。小载荷用例消费 8 个元素，另外两档消费 512 和 8192 个元素。

每个相同载荷/种子的四项组合接收值相同、计算输出逐位相同，共 6 组。交换页的用例在真实物理读地址上体现第 0/1 页对调；每项迁移读、写各 8192 B。原映射用例迁移量为 0。

## 负向检查

六项均调用真实 CA 后端并获得对应拒绝，不是仅检查 Python 函数：

- 过期映射代际；
- 两个逻辑页别名到同一个物理帧；
- 移动字节数超过给定预算；
- 使用分区原帧池之外的帧；
- 调用已经禁用的旧 NoC RPC7；
- 要求后端时钟倒退。

逐项核对后端原始错误输出、无迁移请求开始、无映射发布。网络传输失败/等待失败不能提前发布目的数据等另外 8 项接口单元测试继续通过；单元测试中的 stub 不计作真实仿真次数。

## 独立审计

`audit_small_validation.py` 不导入集成实现或 NumPy 数值内核，从运行目录的实际输入、接收和消费者输出字节重新检查：

1. 用 Python `struct` 独立计算 FP32 向量加法的期望字节，24 项逐位相同。
2. 核对 137,280 条 DRAM 请求及对应回调，ID 无重复，地址/长度/对象/代际/读写/迁移身份一致，完成不早于请求；单事务不超过 32 B。
3. 检查每条源读取确实使用相应物理映射，不从未移动的逻辑副本返回。
4. 从实际 NoC 日志检查数据包、接收就绪控制、CS flit/信用守恒和接收完成时刻。
5. 检查目的写回不早于网络完成，消费者开始不早于目的数据就绪；旧内嵌 NoC 未被重复调用。
6. 检查运行期间代码、二进制、配置及关键依赖哈希未变。

回执：[运行状态](evidence/SMALL_VALIDATION_STATUS.json)、[独立审计](evidence/SMALL_VALIDATION_AUDIT.json)。原始日志和人工诊断载荷保留在集群 `ca_noc_integration_20261108/small_validation_with_payloads/`，没有上传 GitHub。

第一次矩阵同样通过；随后增加原始载荷留档，在另一个新目录重新运行并完成独立审计。两次目录均保留，未覆盖第一次结果。

## 复验

使用已构建的隔离 CA 后端及已验收 NoC，参数与 `probe.py` 相同：

```bash
python3 integration/ca_noc_20261108/small_validation.py \
  --ca-root snapshots/remote/ca_p0_1b_native_20261103_v11 \
  --build /path/to/ca-build --noc /path/to/accepted/popnet_cs_ni \
  --graph noc/20261108/configs/noc_mesh_4x4_v3_6_candidate.gv \
  --ram-config noc/20261108/configs/ramulator2_hb_partition_v3_6_candidate.yaml \
  --npu-config noc/20261108/configs/npusim_npu_config_v3_6_candidate.json \
  --out /new/small-validation
python3 integration/ca_noc_20261108/audit_small_validation.py --run /new/small-validation
```

## 不能由本轮推出的结论

每次网络调用仍为独立且串行的运行，CS 为静态初始配置，没有测量动态配置成本、持续网络状态、多请求并发或计算通信重叠。本轮没有接通完整 LegoSim 迭代驱动、完整 Qwen/四 benchmark 或在线 CA 策略，不比较拓扑/优化净收益，也不证明全输入死锁自由。

因此当前结论是“小规模集成接口在上述测试范围内正确”，不是“系统已完全合并”。下一步应接持久 NoC、多条 posted receive 及统一应用算子链，再进行相应正确性准入。

# CA–NoC 第一版接口集成

将仓库中 LYC 的物理页映射/真实 HB 数值状态，与 `noc/20261108` 已验收 NoC 的传输完成反馈接在同一条串行数据依赖链上。原 CA 和 NoC 快照保持不变。

## 已实际运行

随后完成 [24 项组合＋6 项拒绝的小规模正确性矩阵](SMALL_VALIDATION_REPORT.md)，独立审计核对了 137,280 条真实 DRAM 请求/回调及原始数值输出；下文保留第一次接口探针说明。

集群隔离目录 `ca_noc_integration_20261108` 的短链通过：

1. 在 CA 后端的真实物理页中写入 80 KiB 诊断权重。
2. 实际 HB 读取后，经受测 Mesh 模拟传输 2048 B；接收和排空后才向目的 HB 写入。
3. 使用 LYC 原 `install_layout` 入口交换同分区两页，实际搬移 8192 B，代际从 0 变为 1。
4. 同一逻辑源地址随后从物理地址 4096 而非 0 读取；经受测 CS0 路径传输同样的 2048 B，载荷哈希与迁移前一致。
5. 目的端原生 FP32 向量加法消费接收对象，512 个结果逐位相同。

实际 DRAM 请求与回调均为 3776，映射安装一次。旧 CA 内嵌 NoC 的包数为 0；两次通信只经过新 NoC，不重复调用旧网络。结果见 `evidence/PROBE_RESULT.json`。该诊断输入不是模型或 benchmark 性能数据，两次通信发生在不同时间，不用于比较 Mesh/CS 收益。

## 集成方式

`build_probe.py` 对从 Git 归档取得的 CA 源码生成隔离构建副本：

- 保留物理页图像、所有权、分区内映射、实际搬页、Ramulator 回调和数值 primitive。
- 移除旧 PopNet 与热管理对象链接，由新 NoC 独立负责通信；不修改热管理工作线。
- 每分区容量改为 2 GiB，16 个分区共 32 GiB；事务与源请求切分改为 32 B；从当前目标 JSON 读取 NPU 配置。
- 禁止旧传输 RPC7。新增 RPC16 只允许时钟前进到实际 NoC 返回时刻，并正常推进 DRAM 时钟。

`transport.py` 保留 CA 的 `send(src,dst,token,stage,payload)` 形式，并提供持有对象的 `send_handles`。实际 CA 映射决定源 HB 字节；受测 NoC 决定通信完成时刻；目的 HB 写回和后续计算不能越过这个完成条件。分区内页搬移仍走原 DRAM/SRAM 路径，不制造额外跨节点迁移包。

NoC 仿真处理头、flit、信用、有限缓冲与接收就绪协议；张量字节在功能后端保存，只有网络完成后才提交目的 HB。并未声称 NoC 在每个 flit 上运算或承载完整张量数值位。

## 当前适用范围

这是已跑通的串行接口探针，**不是四个 benchmark 或完整联合优化系统已经合并验收**。

- 固定页交换用于验证真实地址变化，未宣称运行了训练得到的 CA 布局策略。
- 一次只允许一条 32 B 对齐、最大 32 KiB 的消息；不支持的形状直接拒绝，不截断或静默补数据。
- 每次网络调用为独立、完成后排空的有界运行；CS 为静态初始配置。不能用来研究多消息并发、计算通信重叠或动态配置开销。
- CPU、PCIe、HB 垂直接口和完整调度成本尚未统一验收。32 GiB 容量和 32 B 事务对齐不等于所有时序合同已对齐。
- 该入口是 CA RPC 与实际 NoC 的接口联调，尚未接入完整 LegoSim 的多进程/迭代驱动，不替代之前 NoC 独立通过的 LegoSim 联合验收。
- LYC 原多请求 KV、完整层精度与本轮新增目标事务合同仍需重验；未因短链通过而升级为全模型通过。
- 本轮移除旧网络/热对象是解耦接口，不等于热优化已经接入新 NoC。

## 复核与运行

哈希针对原始字节；获取仓库时应关闭 Git 自动换行转换（`core.autocrlf=false`），不要格式化历史快照。

无外部依赖的接口失败/顺序检查：

```bash
python3 -m unittest discover -s integration/ca_noc_20261108 -p 'test_*.py' -v
```

这里的 stub 只验证接口控制流，不是仿真或性能证据。

真实探针依赖原环境的 NPUSim、Ramulator 头/库，以及已验收 NoC 二进制。源码与构建命令见 `build_probe.py`，不是跨机器一键安装包。所有输出目录必须全新：

```bash
python3 integration/ca_noc_20261108/build_probe.py \
  --ca-root snapshots/remote/ca_p0_1b_native_20261103_v11 --out /new/ca-build
python3 integration/ca_noc_20261108/probe.py \
  --ca-root snapshots/remote/ca_p0_1b_native_20261103_v11 --build /new/ca-build \
  --noc /path/to/accepted/popnet_cs_ni \
  --graph noc/20261108/configs/noc_mesh_4x4_v3_6_candidate.gv \
  --ram-config noc/20261108/configs/ramulator2_hb_partition_v3_6_candidate.yaml \
  --npu-config noc/20261108/configs/npusim_npu_config_v3_6_candidate.json \
  --out /new/ca-noc-probe
```

首轮构建检查发现旧冻结清单包含当前账号不可读的历史热管理对象。本版不尝试改变其权限，而是移除已经不用的旧网络/热对象链接，只链接实际需要且可读的 Ramulator/NPU 依赖。首次失败发生于输出目录创建前，保留在实际工具输出中；后两次构建/探针保留独立目录，没有覆盖。

## 下一步

1. 为 CA 已有跨请求/精度回归补齐 32 B 事务合同，检查全部 RPC 的范围和安全拒绝。
2. 从串行有界探针扩展到持久 NoC 状态、多个 posted receive、共享端口与并发完成事件。
3. 接入一份统一模型/输入的真实算子链，再扩展其余应用；保留精度、事务、时间和地址逐项审计。
4. 接通实际 CA 策略输出及 NoC 配置策略后，才进行统一基线、全方法及消融对照。

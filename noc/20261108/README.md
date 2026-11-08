# NoC 源码与正确性验收 · 2026-11-08

本目录归档目标架构 NoC 的 RTL、PopNet 接入改动、LegoSim/NPU/DRAM 耦合代码、验证脚本及小型验收回执。它独立于原有 CA 与四个 benchmark 快照，不覆盖它们。

## 验收结论

本轮功能、协议和短应用联合正确性验收通过。权威总回执是
`evidence/noc_short_validation_20261108/FAST_CORRECTNESS_ACCEPTANCE.json`。
本次发布副本另完成补丁恢复和六组 RTL 复验，见 [发布检查](RELEASE_CHECK.md)。

| 验收对象 | 已运行范围 |
| --- | --- |
| 配置与数据协议 | 22 项，包括非法包、超时保持冻结与动态切换 |
| CS 连接 | 216 项：单连接、完整置换与非法状态拒绝 |
| CS 部分连接 | 774 项；与上项合计覆盖每个 CS 的全部 107 种非零合法单播匹配 |
| 配置与接收就绪组合 | 4 项；另在测试探针修订版重验原 22 项 |
| 真实 Qwen1.5-MoE | 首个 decoder block 静态 CS；连续两个 block Mesh，分别 3 轮严格闭合 |
| 原生动态短链 | 16 节点、三阶段；绝对/相对反馈均 4 轮严格闭合，关键输出精确相同 |
| RTL / 通用综合 | 11 月 4 日的五组 RTL 回归、五顶层通用综合及 Router/CS 网表回归通过 |

Qwen 联合验收核对实际请求、访存、共享端口、接收缓冲生命周期、消费者依赖及独立 NoC/DRAM 参考；不能将它表述成全模型数值精度验收。短链执行 48 条数据消息、64 条真实 DRAM 请求和 49,152 次原生向量操作，包含实际 NoC 上的配置、应答、排空与接收就绪消息。

这不是所有输入的形式死锁自由证明，不是完整 24 层应用性能验收，也不是完整动态 HiBand 复现或优化策略收益结论。24 层接续队列已退役，不是本轮正确性准入条件。

## 文件组织

```text
configs/                    实际验证使用的目标配置
rtl/rtl/                    CS、选择器、NI、Router 与切换管理 RTL
rtl/tb/                     11 月 4 日回归 testbench
rtl/earlier_tb/              11 月 3 日分模块 testbench
snapshots/                  保持原字节的实验源码快照
patches/popnet/             相对原始 PopNet 的零上下文补丁
evidence/                   小型历史验收回执，不含原始大日志
tools/verify_release.py     文件完整性、语法与验收关联检查
tools/replay_rtl.py         在全新输出目录运行 RTL 回归
tools/restore_popnet.py     从合法持有的原始源码恢复已验收适配树
SOURCE_MANIFEST.json        本次发布文件哈希
REMOTE_SOURCE_MANIFEST.json 集群源码、上游基线及补丁来源哈希
LOCAL_SOURCE_MANIFEST.json  本地 RTL 与回执来源哈希
```

### 推荐阅读顺序

1. 本说明及 `DESIGN_AND_VALIDATION.md`。
2. `rtl/rtl/terminal_switch.sv`、`node_selectors.sv`、`ni_config_agent.sv`。
3. `snapshots/noc_crosslayer_validation_20261108/noc/adapter/changes/`：实际仿真端的 CS、配置协议、接收就绪、共享 SRAM 及因果反馈。
4. 同目录的 `npu/` 与 `core/`，以及 `snapshots/ramulator_wallclock_20261107/`。
5. `snapshots/noc_short_validation_20261108/short_chain.cpp` 和最终验收回执。

## 复核与复验

下列命令在本目录执行；第一条只读，不启动仿真：

```bash
python3 tools/verify_release.py
python3 tools/replay_rtl.py --out /absolute/path/to/a/new/noc-rtl-check
```

第二条要求 PATH 上已有 Icarus Verilog 的 `iverilog`、`vvp`，或用 `--iverilog`、`--vvp` 指定。输出目录必须不存在，失败会以非零状态退出。此入口不安装工具、不连接集群，也不启动长应用。它是重新运行 RTL 测试，不是全系统验收重跑。

恢复 PopNet 适配树：

```bash
python3 tools/restore_popnet.py \
  --upstream /path/to/authorized/popnet_exact_o3 \
  --out /path/to/new/popnet-adapter
```

此入口先核对基线源码 SHA256，再在新目录应用补丁并核对最终 SHA256；不会修改上游原目录。它需要系统 `patch` 命令和合法持有的对应源码；不是从互联网自动下载依赖。

### 联合仿真的依赖边界

`snapshots/` 中原脚本保持实验时字节，包含历史绝对路径、同级目录依赖及构建副作用，不能直接批量执行。它们用于定位实际实现，不是跨机器一键运行入口。重跑须在隔离目录恢复相应依赖、模型输入与原验收命令，不得覆盖历史证据。

所需外部组件包括 Linux C/C++ 工具链、CMake、Boost、yaml-cpp、CLI11、spdlog、NPUSim 及其 ONNX/Protobuf、Ramulator2、InterChiplet SDK 与合法的 PopNet/ORION 基线。具体 CMake 依赖保留在快照内。Qwen 权重、算子计划、输入张量和完整 Trace 未收录；尚未完成无集群依赖的全工具链干净安装验收。

RTL 与 C++ 仿真模型分别验证，不能据两者都有 PASS 宣称已经完成全网络 RTL/C++ 逐周期形式等价。没有 Liberty 工艺库，通用逻辑综合不代表物理面积、功耗、1 GHz 时序或布局布线签核。

## 来源、历史与权利

原始实验不因归档而改写；文件哈希可关联原始证据。`evidence/` 是历史回执副本，不会因为复制到本仓库自动成为新运行结果。两个来源清单保留原路径作来源定位，不能把其中路径当公共机器地址。

旧 PopNet/ORION 树存在再分发限制，所以不上传完整 vendor 源码、graph_lib 或 ORION；只归档项目新增适配模块、必要集成补丁与基线哈希。没有为第三方代码或本项目新增开源许可，使用仍遵循原有权利和授权。

首次短链审计错误地要求接收请求时刻等于发送请求时刻；后续审计分别核验真实读/写请求。另一次汇总因反馈文件名不一致失败；最终比较使用实际文件名，未修改仿真结果。配置组合测试只修正重复 ARM 诊断探针的触发条件，生产仿真源码不因此更改。详见 `DESIGN_AND_VALIDATION.md`。

未收录密钥、账号凭据、模型、数据集、完整应用 Trace、大型日志、运行二进制、工具安装包和进程清理/后台自动接续脚本。

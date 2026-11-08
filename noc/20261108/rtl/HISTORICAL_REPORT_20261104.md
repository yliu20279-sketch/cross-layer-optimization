# NoC RTL 通用逻辑综合与网表回归（2026-11-04）

## 1. 本轮结论

已在原集群 SERVER-113 实际完成五个模块的 Yosys 通用逻辑综合，并重新运行五组 RTL 回归和 Router、CS 两组综合网表功能回归。全部通过，退出码均为 0。

本轮延续“先验证硬件实现，再接完整仿真器”的工作顺序。所有文件在新的独立目录中，未覆盖原仿真、论文、旧结果或前几轮验证目录。当前目录的 10 个 RTL 文件与上一轮 `noc_aux_port_20261104/rtl` 逐文件 SHA256 一致。

没有指定工艺 Liberty 库，因此本轮不报告平方微米面积、功耗、可达频率或时序收敛，也没有产生新的应用性能数据。

## 2. 工具与执行位置

- 集群目录：`/mnt/sdb1/h4567/noc_generic_synthesis_20261104`
- 实际执行主机：`SERVER-113`，Python 3.8.10。
- 综合版本：`Yosys 0.55 (git sha1 60f126cd0, ccache clang 18.1.3 -O3 -flto -flto)`。
- 安装方式：独立目录 `tools/py` 内的 `yowasp-yosys==0.55.0.0.post944`、`yowasp-runtime==1.92`、`wasmtime==25.0.0`。这是 YoWASP 提供的 Yosys WebAssembly 分发，不是本项目自行编写的综合模型，也不是 YosysHQ 的原生二进制发行包。
- HDL 仿真：前几轮已安装的 Icarus Verilog 13，正常 Linux `iverilog` / `vvp` 命令。
- 工具仅安装到任务目录，没有修改系统 Python 或全局工具。

`install_report.json` 留存实际安装信息，综合记录保存 7 个 wheel 的 SHA256。完整 wheel 和工具安装在集群；本地保存结果、源码和安装清单，不复制整套工具运行时。

## 3. 参数与统计结果

数据宽度为 256 bit。Router 是当前功能原型的每输入深度 2 FIFO，节点编号 5，关闭调试端口；两种 Router 使用同一 RTL，区别仅为 AUX 输出启用与否。选择器与受控 NI 也取内部节点编号 5。

| 综合顶层 | 硬件通用逻辑单元数 | 其中触发器单元 | 组合逻辑单元 | 锁存器 | 组合强连通环 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Router，不启用 AUX | 30,206 | 2,615 | 27,591 | 0 | 0 |
| Router，启用独立 AUX 输出 | 35,672 | 2,622 | 33,050 | 0 | 0 |
| CS 开关 `terminal_switch` | 11,720 | 0 | 11,720 | 0 | 0 |
| 节点发送/接收选择器 | 5,402 | 0 | 5,402 | 0 | 0 |
| 配置与冻结/计数管理端点 `managed_endpoint` | 5,406 | 622 | 4,784 | 0 | 0 |

在这份原型 RTL、参数和综合流程下，启用 AUX 相比同核关闭 AUX 增加 **5,466 个通用单元**，其中 7 个触发器、5,459 个组合单元。它反映当前实现表达式经过通用映射后的规模，不是等效 NAND 门数或芯片面积；不同类型单元不能视为等面积。此处关闭 AUX 的 Router **不是 HiBand Split-Benes 的物理成本基线**，不能据此给出“相对 HiBand 的面积开销”。

CS 和选择器计数包含当前 RTL 中的配置合法性、可变选择及流控组合逻辑，不只是示意图中 MUX 图标的数量。因此本轮保留实际综合结果，没有为得到较小数字而改写 RTL。后续若固定化选择结构或移动检查逻辑，必须另存版本并重做行为验证。

原始 JSON 还含有 `$scopeinfo` 对象：两个 Router 各 1 个，管理端点 2 个。它们保存 flatten 后的层次属性，不是电路单元；表格已单独扣除，原始统计和网表未修改。依据为 [Yosys flatten 官方说明](https://yosyshq.readthedocs.io/projects/yosys/en/docs-preview-ci/cmd/index_passes_hierarchy.html)。原始及剔除后的数量都可在 `build/generic_summary.json` 查到。

## 4. 具体做了哪些检查

### 4.1 综合结构检查

每个顶层均经过：SystemVerilog 读取、层次检查、通用 `synth`/ABC 映射、flatten、清理、`check -assert`、锁存器拒绝检查、`scc -expect 0`，然后输出 JSON/Verilog 网表。

五个顶层均返回 0；最终结构检查均报告 0 problems，锁存器和组合强连通环均为 0。日志中的数组转寄存器警告保留：它表示此流程将相关存储结构展开为逻辑/触发器，未使用 SRAM 宏面积。CS 内部临时数组也出现这一前端提示，但最终 CS 没有触发器或锁存器。

各模块内部没有组合环，不等于整个网络已经获得死锁自由证明；尤其跨模块流控和真实 VC 资源仍须在实际仿真器内核对。

### 4.2 RTL 回归：五组通过

| 测试 | 实际结果 |
| --- | --- |
| 编译器冒烟和负例 | 正常 HDL 执行成功；故意加入的语法错误被编译器拒绝 |
| 独立 AUX Router | 160 路由情况、2,490 载荷逐位检查；不同输入的 Local/AUX 同周期发送；AUX 阻塞时 8 个控制包正常前进；同输入 FIFO 的队头阻塞仍明确存在 |
| 正常配置切换 | 3,072 flit 注入并退休，其中 2,880 辅助；顺序、载荷和守恒检查通过；覆盖旧包在途、credit 返回及冻结期间普通包继续传输 |
| 超时路径 | credit 故障注入后，16 个源保持冻结，旧配置保持，不错误提交 |
| 管理边界 | 重复 ARM 不清除计数；新 epoch 数据已到达时 RUN 正常；计数阈值故障阻止提交 |

输出见 `build/verification.json`、`build/*_simulation.log`。记录的实际执行主机为 SERVER-113，不是仅复制上一轮 Windows 通过状态。

### 4.3 综合网表功能回归：两组通过

- Router：直接编译两种综合后 Verilog 网表，复用外部端口行为测试，160 路由、2,490 逐位检查以及并发/阻塞检查全部通过。综合封装没有调试 FIFO 计数端口，故该内部调试断言不在网表分支中，其余外部行为检查保留。
- CS：综合网表覆盖 1,048,576 个配置/输入 valid 组合；108 个合法和 3,988 个非法配置、3,072 个数据逐位检查全部通过。

这是已执行测试范围内的综合网表功能回归，不是全输入、全时序的形式等价证明。选择器与管理端点本轮完成综合及 RTL 回归，未单独进行综合网表仿真。

## 5. 如何独立复验

进入原集群任务目录：

```bash
cd /mnt/sdb1/h4567/noc_generic_synthesis_20261104
python3 tool_command.py -V
bash run_pipeline.sh
bash run_final_checks.sh
python3 analyze_and_audit.py
```

第一条流水线运行 RTL 回归及综合；第二条重跑 RTL 和 Router/CS 网表测试。审计脚本核对 23 份 RTL 测试输入哈希、13 份综合输入哈希、五组综合产物哈希、两组网表测试输入哈希，并从实际 JSON 网表重新计数。集群另核对 7 个工具 wheel 哈希；本地没有 wheel 时明确记录验证数为 0，不假称已本地验证工具包。

只有以下条件全部成立，才认定本轮通过：

1. `build/pipeline.exit`、`build/final_checks.exit`、`build/runner.exit` 都是 `0`。
2. `build/synth/synthesis_status.json` 为 `passed_generic_synthesis`。
3. 两份 `verification.json` 的 `all_passed` 都为 true。
4. `check_artifacts.py` 和 `analyze_and_audit.py` 均通过，日志/源码/网表哈希匹配。

本地只核对已回传证据，不需要安装综合工具：

```powershell
& 'C:/Users/14284/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' 'work/noc_generic_synthesis_20261104/analyze_and_audit.py'
```

`generic_summary.json` 中 audit_host 是执行审计的机器，synthesis_host 才是原始综合主机，二者不能混用。两地审计副本分别另存为 `generic_summary.local.json` 和 `generic_summary.cluster.json`。

## 6. 下一步

本轮证明这些硬件模块可以被综合工具转换成通用逻辑网表，且已运行的回归没有出现行为错误。目标架构的完整 NoC 实现与应用性能验证尚未由这些检查替代。

后续按下列顺序继续：

1. 对齐实际 PopNet 的节点坐标、物理端口与 VC/HEADTAIL/CREDIT 语义，再定义独立 AUX 端口适配。现有 C++ 中端口 5 可能已有芯粒内部含义，不能直接覆盖。
2. 将已经验证的单 AUX 通道、CS 互斥连接、NI 接收/写入瓶颈和配置切换开销接入工具链；保持目标架构 16 NPU，不改成小节点架构代替。
3. 在同一真实 trace、相同物理资源约束下进行完整 LegoSim–PopNet 对照，评估热点、排队、端到端时间及计算通信重叠。已有 RTL 功能周期不能代替这些数据。
4. 工艺库确定后再进行技术映射、静态时序和面积/功耗评估；当前通用单元数不写成物理 PPA。

本轮任务均已结束，没有需要继续等待的综合或验证后台进程。没有更新论文数据或图片。

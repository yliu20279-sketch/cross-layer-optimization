# 表 V 的 NoC 配对 RTL 与结果

同一顶层 `noc_paired` 通过 `ENHANCED=0/1` 选择固定 Mesh 或 Mesh + 13 CS。两组均为 4 × 4 Mesh、16 个端点、256 位 flit。增强版含下层 9 个、上层 4 个电路交换节点，每个 CS 内有一级寄存缓冲，集中控制在旁路排空后提交新配置。原型包含简化 NI，范围限于 NoC 核心，不含完整 DMA、SRAM Bank 控制、热管理、HB PHY 及跨裸片物理互连。

## FPGA

见 [RTL、testbench、Vivado 脚本及报告](noc_paper_vivado_20261114)。`RTL_onehot.log` 记录 256 个 Mesh 端点对、108 条下层 CS 路径、24 条有向上层路径，以及非法闭环拒绝与背压排空切换。Vivado 2017.4，器件 xcku5p-ffva676-2-e，使用 5 ns 时钟约束，采用 OOC 实现。FPGA 时序来自布线后 STA。没有板卡实测频率。

历史实施入口为 `run.ps1 -Vivado <vivado.bat> -WorkDir <新的 ASCII 路径> -IcarusBin <Icarus 工具目录>`。此脚本完成 RTL 回归及综合。在生成的工作目录用 `vivado -mode batch -source route.tcl -tclargs 0` 和 `... -tclargs 1` 分别布线。`collect.py` 从随附报告重建 `TABLE_V_FPGA.csv`。报告副本已去除主机名和本机目录。

## ASIC

见 [ASIC 使用的 RTL、约束、流程脚本及表 V 数据](noc_table_v_asic_20261114)。Nangate45 TT（1.10 V，25 °C），Yosys 0.23、Berkeley ABC、OpenROAD v2.0-17598-ga008522d8。功耗为 OpenSTA 无向量估算，时钟约束 1 ns、活动率 0.10、占空比 0.50。布线后动态功耗为内部功耗与开关功耗之和。两组详细布线均为 0 个路由 DRC 标记，OpenRCX SPEF 经独立重读，带负载但未标注的驱动均为 0。

实际消费的 RTL 按平台各自保存。ASIC 流程所用 Nangate45 库及 RC 文件来自 OpenROAD-flow-scripts 提交 `73c804d45dc4084b05e0536dab69053b3bf9e591` 的 `flow/platforms/nangate45`。映射入口见 `map_0.ys`、`map_1.ys`，物理版本映射后使用 Yosys 的 `setundef -zero` 和 `hilomap -singleton -hicell LOGIC1_X1 Z -locell LOGIC0_X1 Z`。最终详细布线入口是 `run_arm_113.sh`，需要原实验的 OpenROAD 镜像及相应的布线前 ODB 和 guide。最终 ODB、SPEF 和原始提取报告保存在实验归档，仓库中的 `result_*.sha256` 可用于核对这些原件。

| 表 V 指标 | 固定 Mesh | Mesh + 13 CS |
| --- | ---: | ---: |
| FPGA 布线后 LUT | 26,893 | 37,441 |
| FPGA 布线后 FF | 21,025 | 24,451 |
| FPGA 布线后 setup WNS，5 ns 约束 (ns) | +0.528 | +0.290 |
| ASIC 综合后标准单元面积 (mm²) | 0.205446 | 0.250919 |
| ASIC 综合后总功耗 (W) | 1.46 | 1.65 |
| ASIC 布线后标准单元面积 (mm²) | 0.359453 | 0.458480 |
| ASIC 布线后动态功耗 (W) | 0.661 | 0.721 |
| ASIC 布线后漏电功耗 (mW) | 11.7 | 15.2 |

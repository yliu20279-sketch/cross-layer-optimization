# NoC Design 论文修订 v3（2026-11-09）

主文件：[main_draft1109_design_hardware_v3.tex](main_draft1109_design_hardware_v3.tex)。

编译结果：[PDF](main_draft1109_design_hardware_v3.pdf)。使用 pdfLaTeX、BibTeX、pdfLaTeX 两次编译；图片与两个参考文献库均已随目录提供。

## 本轮修改

- 明确每个下层 CS 物理连接四个角节点的 NI，不是只连接两个 NI。
- 一次本地连接选一个面向节点的输入与另一个面向节点的输出；接入上层则选择一个面向节点的方向和 U。
- 下层本地路径无需经过上层；上层提供四个 U 接入下层 CS 之间的额外路径。
- 两级 CS 在同一逻辑 die 内实现；图中上下平面表示连接层级。
- 无 U 接入的五个下层实例采用固定接零和 U 输出使能屏蔽，不依赖软件默认值。
- 短程 CS 路径增加 Mesh 之外的数据通道，吞吐仍受 NI 和 SRAM bank 带宽约束。
- 删除未解释的 F 符号与位图公式，说明 NI 分包、按偏移写回和接收记录。

本目录只重写 Design，预测、问题定义、配置算法和热管理在源码中留有注释占位。Design 之外保留同学原稿，包括旧 Motivation 示例和实验占位，尚需后续统一；本目录不是投稿终稿。图纸和 RTL 未因本轮文字修改而改变，未接 U 的硬件约束是补充实现要求，不能视作已经通过 RTL 验证。

## 来源和检查

原稿来自 `codex/paper-ieee-draft-20261109` 分支提交 `d3eb68ea8332de8d3722f18406ca669ef09282dc` 的 `DAC_SWDefined3DIC/main_draft1109.tex`，未覆盖原稿分支。

图源来自同分支的 [两级 CS 图纸](../20261109_two_level_cs/README.md) 和 [Node/NI 图纸](../20261109_node_ni/README.md)。其中 PDF 图资产由 `prepare_figure_pdfs.py` 转换。

`main_draft1109_design_hardware_v3_check.json` 记录本地修改范围、引用、资源哈希及编译检查；这是文稿检查，不是 RTL、时序或实验结果验收。

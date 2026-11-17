# NoC Design 与算法本地改稿

基线：GitHub `yliu20279-sketch/cross-layer-optimization`，分支 `codex/paper-261115-revision-20261117`，提交 `4f6dd19e767964d0c47da271c1dd4d32c570d909`，提交时间为北京时间 2026-11-17 22:43:29。

本地分支：`codex/dual-plane-noc-design-20261117`。

重写 Design 中的双平面结构、节点与 NI、CS 电路、预测、配置问题、配置算法和配置接口。GetS/DataS 按类型进入 C，MoE 数据及控制进入 M；端点存储仲裁共用。原两张设计图的正文引用改为一张最新 Visio 组合图，编号 Fig. 4，位于第 4 页。

同步了引言中的架构概述和旧硬件成本表的适用范围；表内实验数值保持原样。Thermal-Aware Execution 内容保持原样。

本轮进一步重画机会图 Fig. 3，并改写对应 Motivation 段落及图注：左侧展示 GetS 与 MoE 共用出口，右侧展示 GetS/DataS 经 C0-C4-C8 及 MoE 的 Mesh/NI5-CS3-NI8 路径。旧机会图和旧时序示意不再用于正文。基线说明及摘要中的方案概述同步为 M/C 双平面。

机会图右侧现使用完整拓扑：16 个 N 节点、16 个 C 路由器、9 个下层 CS 和 4 个上层 CS，保留全部物理连接。绿色标注 GetS/DataS，橙色标注 MoE Mesh 路径，蓝色标注 MoE CS 路径。机会图由 Visio 原生形状绘制；figures/noc_opportunity_dual_plane.vsdx 是可编辑源文件，.png 为预览，.pdf 为论文使用的矢量图。

2026-11-18 算法修订：GetS/DataS 固定走 C 平面 XY；MoE 保留流量最大化、排序及 CS/普通 Mesh 分配。合并重复公式与表述，保留完整包唯一分配、CS 互斥、共享服务预算、完成时间和配置成本检查。NI 确认暂停后再刷新并复核，配置写入与描述符安装均以确认结果为准。

已完成 pdflatex、BibTeX 和交叉引用编译，成稿 9 页。机会图位于第 3 页，设计图位于第 4 页；算法正文与伪代码集中在第 5 页。逐页检查了修改涉及的正文与图页，两图完整显示，图中文字保持矢量。原始下载稿保存在 baseline/，上轮算法稿保存在 before_algorithm_update/。

工程入口为 DAC_SWDefined3DIC/main_draft1115_review.tex，算法与预测文字位于 noc_prediction_configuration.tex。压缩包包含当前使用的图片、参考文献、PDF 和新图的可编辑 Visio 文件。

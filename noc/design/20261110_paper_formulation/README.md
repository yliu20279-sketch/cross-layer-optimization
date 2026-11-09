# NoC 论文问题定义与配置算法 v5

2026-11-10 更新。最新主文件：[main_draft1110_noc_formulation_v5.tex](main_draft1110_noc_formulation_v5.tex)。[编译 PDF](main_draft1110_noc_formulation_v5.pdf)。

## 本次修订

- III.D 明确定义路径选择 z_p 和整包分配 x_m_p；目标为最大化分配到可重构网络的有效载荷总量。
- 逐项写出唯一分配、启用、接纳、CS 互斥和共享服务预算约束。Mesh 回退的数据仍计资源开销。
- 把路径变量映射为每个 CS 的输入、输出和使能；把包分配映射为 NI 的发送路径标签。
- III.E 按通信量排序并逐轮扩展兼容电路，保留带注释的伪代码。完成时间和配置开销单列为应用前复核。
- K_f / K_p 仅限制每轮候选搜索规模，没有测得的推荐数值，不是老师指定参数，也不是 MoE Top-K。上一轮口头说明未另改源码，本次上传的是核对过的 v5。
- 摘要目标与 NI 描述符文字同步更新。硬件图、RTL、实验原文及热管理占位未改。

## 文件入口

- [问题定义与算法中文对照](问题定义与算法_中文对照.md)
- [组会要求逐项核对及写法参考](组会要求逐项核对.md)
- [英文新增正文与伪代码](noc_prediction_configuration.tex)
- [13 项微型约束检查](formulation_unit_checks.json)
- [文稿范围、引用与编译检查](v5_check.json)

编译时保持算法正文 TeX 与主文件同目录，并保留两个 bib 文件和整个 figures 文件夹。使用 pdfLaTeX、BibTeX、pdfLaTeX 两次。

本目录是文稿和模型定义。约束示例、静态路径及编译通过不代表在线控制器、RTL、工艺时序或应用收益已经验证。全文仍为 10 页，尚未最终压页；Design 之外仍保留原稿及实验占位。

## 来源

论文从前次 v4 工作稿修订，v4 又基于 `d3eb68ea8332de8d3722f18406ca669ef09282dc` 的同学原稿。图纸来源见 [CS 拓扑图](../20261109_two_level_cs/README.md) 和 [Node/NI 图](../20261109_node_ni/README.md)。本目录保留 v3 发布目录，不覆盖同学的论文分支。

`audit_v5.py` 的修改范围核对依赖本地留档 v4 路径；不要将它误认为脱离原稿也能独立运行的构建步骤。`check_formulation.py` 和 `check_algorithm_paths.py` 可以在本目录独立运行，只生成其明确范围内的检查报告。

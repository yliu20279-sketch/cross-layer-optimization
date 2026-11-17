# 2026-11-17 Qwen1.5-MoE 高频 GetS 实验发布

[实验报告](README.md)记录原始 HiBand 参考、RTL 候选筛选、三档 OPP 标定、NoC＋Thermal、NoC-only 和同后端四臂配对的结论及各自的适用范围。[最终配对回执](paired_native_results/SUMMARY.json)记录冻结的 256／512 笔输入指纹、共同后端、两臂逐笔轨迹校验和比较结果。

## 113 上的运行记录

| 归档 | 内容 |
|---|---|
| [01-hiband-reference](evidence_113/01-hiband-reference.tar.gz) | 两档初始 HiBand 参考、合同、包与回调记录 |
| [02-rtl-and-thermal-inputs](evidence_113/02-rtl-and-thermal-inputs.tar.gz) | RTL 候选筛选、实际使用的 Thermal 输入及重建系数 |
| [03-opp-and-joint-thermal](evidence_113/03-opp-and-joint-thermal.tar.gz) | 三档 OPP、放行探针、后端接入检查及两档 NoC＋Thermal |
| [04-noc-only](evidence_113/04-noc-only.tar.gz) | 两档无 Thermal 的筛选及原生混跑 |
| [05-native-pair](evidence_113/05-native-pair.tar.gz) | 两档各两臂、匹配的输入与后端配置、逐笔时序和结果 |

五个归档共包含 571 份本轮记录。[逐文件清单](evidence_113/MANIFEST.json)提供成员路径、字节数、SHA-256 和未打包项清单。下载后可在 `evidence_113` 中用 `sha256sum -c SHA256SUMS` 校验。原始路径和镜像引用用于追踪来源。可重建工具、对象文件、运行二进制、缓存及重复下载包按清单保留在原实验环境。模型权重和通用运行环境由原实验环境提供。Thermal 上游采用 [bcbee2c4](https://github.com/yliu20279-sketch/cross-layer-optimization/tree/bcbee2c4/thermal)。

在本目录运行 `python -B audit_paired_native.py . paired_native_results` 可从版本化的逐笔 GetS 和算子时序重新核对最终配对。

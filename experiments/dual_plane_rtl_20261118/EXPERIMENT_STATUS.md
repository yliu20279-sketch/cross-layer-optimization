# 共同实验基准（2026-11-18）

本次提交包含双平面 RTL、HiBand NoC 适配版、共同端点、复现脚本、分工计划及 312 组结果。双方以本次提交为共同版本，并登记 Git 提交号。

- 功能回归与 312 组回放通过，共 1,872 个通信阶段；原始回执在 `evidence/`。
- 测试构建编号为 `57a5a3a629cdcf68_1b0d9532209a`。主源码与回执中的 SHA-256 一致；相同配置等待的 Mesh 对照使用单独入口，复用该构建的 RTL 库。
- 双平面关闭 CS 相对 HiBand 适配版逐阶段理想最优模式，阶段总时间几何平均加速 1.0237 倍；在线控制原型没有提交更新。详见 `evidence/results/REPORT_CN.md`。
- 结构综合尚未通过：已记录退出码 137，采集时其余检查状态见 `evidence/SYNTHESIS_SNAPSHOT.json`。日志片段一并保留；面积、物理时钟与布线结果未验收。

先运行 `python3 verify_package.py` 核对文件与测试源码，再运行 `python3 analyze.py --evidence evidence --output analysis_review` 独立重做统计。归档文件保持原样，新统计写入单独目录。恢复输入与重新运行方法见 README；刘宇晨的工作范围见 `EXPERIMENT_PLAN_CN.md`。

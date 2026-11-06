# Qwen1.5-MoE-A2.7B 算子图与 V3.6 映射

## 结论边界

本目录给出可复现的解析级算子 DAG、通信事件和 V3.6 静态映射。它不是框架 trace，也不是芯片实测：运行时、NoC 延迟、功耗和温度均未执行或验证。

## 已确认的模型事实

- 24 个 decoder layer，hidden size 2048，16 个 attention head 和 16 个 KV head。
- 每层 60 个 routed experts，Top-4；expert intermediate size 1408；shared expert intermediate size 5632。
- 模型卡给出的规模为总参数 14.3B、每 token 激活 2.7B。本生成器按配置公式得到 14,315,784,192 和 2,689,173,504，分别与上述舍入值一致。

来源：

- [Qwen 官方模型配置](https://huggingface.co/Qwen/Qwen1.5-MoE-A2.7B/raw/main/config.json)
- [Qwen 官方模型卡](https://huggingface.co/Qwen/Qwen1.5-MoE-A2.7B/blob/main/README.md)
- [Transformers Qwen2-MoE 实现](https://github.com/huggingface/transformers/blob/main/src/transformers/models/qwen2_moe/modeling_qwen2_moe.py)

## 图生成口径

生成 prefill（Q/K=4096）、first decode（Q=1、K=4097）和 incremental decode（Q=1、K=4352）三张 DAG。每张图包含 embedding、24 层 attention/MoE、final norm、LM head 与 TopK；attention score 被切片表达，不实体化完整 score tensor。路由图表示 Top-4 数据依赖，不声称获得了真实 token-to-expert 分布。

| 阶段 | 节点 | 边 | useful MAC |
|---|---:|---:|---:|
| Prefill | 679 | 870 | 9,289,721,446,400 |
| First decode | 679 | 918 | 2,780,463,104 |
| Incremental decode | 679 | 918 | 2,805,530,624 |

## V3.6 映射

- 并行策略：attention/nonexpert 采用 TP16；routed experts 采用 EP16；每个 NPU cluster 与同号 HB channel/partition 纵向绑定。
- 16 个 cluster 各持有一个 attention/KV head，并共同执行 shared expert。
- 专家权重不是沿用 V3.5 的固定 expert-ID 分配，而按 `cluster=(layer*60+expert)%16` 放置。因此 24×60=1440 个层特定 expert 权重实例精确均分为每 cluster 90 个。
- Top-4 激活发送到选中专家的 owner；结果再返回并加权合并。CSV 只描述解析通信量，不代表 NoC 仿真延迟。

## 容量可行性及限制

V3.6 提供 16×512 MiB=8 GiB。以 W4 理想权重存储、BF16 KV cache、上下文 4352 为口径，每分区估算：embedding+LM 18.55 MiB，nonexpert 36.85 MiB，90 个 expert 权重实例 371.25 MiB，KV 51.00 MiB，另留 32 MiB 元数据/激活/DMA/分配器综合预留；合计 509.64 MiB，余量仅 2.36 MiB。

因此结论是“有条件静态可放置”，不是“已完整执行”。若真实 W4 格式的 scale/zero-point、对齐、双缓冲等超过 32 MiB，仍会溢出，需要增大分区、减少驻留权重或引入分层换入。HB 带宽仍为 25.6 GB/s；增容没有自动消除带宽瓶颈。

## 复现

~~~powershell
C:\tool\Miniconda\python.exe .\build_v3_6_mapping.py --out .\generated
C:\tool\Miniconda\python.exe .\render.py --generated .\generated
C:\tool\Miniconda\python.exe .\validate.py --root .\generated
~~~

`generated/` 内含三阶段 JSON/节点 CSV/边 CSV、NPU-SIM IR、NoC traffic、逐层专家放置、容量报告、映射 manifest、V3.6 源文件哈希快照以及 PNG/PDF/SVG 图。验证器检查 DAG、层数、非实体化 score、容量、专家均衡、未宣称执行及 V3.6 源文件未改动。

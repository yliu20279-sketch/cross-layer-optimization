# HiBand 复现状态

更新时间：2026-08-28

## 总体判定

`PARTIAL - 步骤4–6的独立解析参考分别达到PASS_LIMITED、PASS_LIMITED_ANALYTIC、PASS_LIMITED_REFERENCE；作者artifact、split-Benes、厂商DRAM和论文数值对齐仍不可得。`

## 分项状态

| 对象/声明 | 状态 | 依据 | 下一门禁 |
|---|---|---|---|
| HiBand论文身份 | PASS | 本地全文、DAC正式页面、DOI | 无 |
| HiBand架构定性事实初审 | PASS | 已阅读全文和关键页面视觉核验 | 转入逐参数提取；不等于架构复现PASS |
| HiBand官方代码/RTL | BLOCKED | 定向检索未发现 | 作者仓库、补充材料或作者确认 |
| HighBand名称映射 | PARTIAL | 高概率为HiBand转写，但未获确认 | 用户/会议原始记录确认 |
| H2-LLM论文身份 | PASS | 作者PDF、DOI | 无 |
| H2-LLM官方artifact身份 | PASS | 官方GitHub、Apache-2.0、提交已冻结 | 克隆后复核LICENSE与commit |
| H2-LLM artifact smoke | NOT STARTED | 阶段0禁止安装和执行 | 单独批准实验卡 |
| 3D-TANoC论文身份 | PASS | ISCAS正式程序、DBLP/DOI交叉核验 | 获取全文 |
| 3D-TANoC全文核验 | BLOCKED | 当前只有正式元数据和有限摘要，无可核验本地全文 | 获取合法全文 |
| TODOLIST中TANoC映射 | PARTIAL | 高概率为3D-TANoC，但文档未写全称 | 用户确认 |
| 3D-TANoC官方代码 | BLOCKED | 定向检索未发现 | 作者仓库或作者确认 |
| 113服务器只读盘点 | PASS | 主机、Python、LEGOSIM提交、脏工作树及磁盘状态已留证 | 共享工具链继续只读 |
| 项目双网络定义 | PASS | `spec/project_dual_network.md`；明确为项目概念而非论文术语 | 后续用真实trace验证 |
| HiBand与项目双网络映射 | PASS | `spec/hiband_reference_mapping.csv`；明确不预设等价 | 后续实验验证映射 |
| HiBand独立微型模型 | PASS（限定） | 本地和113均通过10项测试；仅为GTP/HIC上界/SOR账本/抽象NoC | 不等于作者功能模型 |
| 113可移植性smoke | PASS | Stage7在SERVER-113完成44项测试；request/fair A/B字节级一致；证据包SHA-256为`0125e4ae90964c1718cfe248627eb8d8955558ffac8ccb92c75dac49ca9910cb` | 该PASS只证明参考模型可运行、可重复 |
| GPT-2-Large单层解析账本 | PASS（限定） | 24项本地/113测试；远端A/B哈希一致 | 尚不含elementwise和完整驻留策略 |
| Llama/Mixtral公式账本 | PARTIAL | 已加入GQA、gated MLP、MoE router公式测试 | 尚未生成完整场景trace |
| GTP组间PP | PARTIAL | 两层及多层已加入跨stage activation edge | 仍需microbatch、fill/drain、stage-ready和真实调度 |
| SCALE-Sim接口 | PARTIAL | 32×64假设配置的8×8×8 GEMM smoke通过（133 cycles） | GPT-2四大GEMM直接运行超过门禁时间并中断，需分层/优化运行 |
| DRAM/NoC联合模型 | PARTIAL | 解析队列、单调性和参考耦合测试通过 | 尚未接真实任务图和包级NoC |
| Compute/HB/NoC参考DAG | PASS（限定） | HB read/write及FG跨stage序列化进入关键路径；35项本地/113测试通过 | eager read、合并write、预取均为假设；不是论文调度器 |
| 11场景矩阵 | PASS（参考账本） | GPT-2/Llama/Mixtral单层及完整层数参考场景在113运行 | 不是完整推理，TTFT/TPOT保持不可计算 |
| HIC/SOR/四模式组件表 | PARTIAL | FG回退语义、HIC上下界、SOR存储区间和模式切换组件已生成 | 尚未形成同一DAG上的公平总时延消融 |
| 论文趋势比较 | PARTIAL | 方向/不可比原因表已生成，numeric_comparable=false | 缺作者artifact和私有模型，不能数值对齐 |
| HiBand步骤4：统一DAG公平消融 | PASS_LIMITED | 唯一`build_variant_dag()`；固定工作量/硬件；显式HB、TP/PP、HIC、SOR和静态NoC switch；MAC/HB/NoC账本测试通过 | 仅独立解析DAG，不是作者调度器 |
| HiBand步骤5：工具与模型场景 | PASS_LIMITED_ANALYTIC | GPT-2/Llama请求、固定batch流水、Mixtral单层expert DAG完成；计算/HB/NoC进入同一scheduler | SCALE-Sim/PopNet仍仅部分校准且未进入makespan |
| HiBand步骤6：指标与趋势 | PASS_LIMITED_REFERENCE | B0–B4统一参考消融、TTFT/TPOT、资源分项、switch敏感性和趋势表；Stage10在113通过62测试，本地/远端结果哈希一致 | `numeric_comparable_to_paper=false`，不证明论文趋势 |
| HiBand性能复现 | PARTIAL（独立参考模型） | 已有解析/事件模型、请求参考、代理工具证据；不具备作者artifact与参数闭环 | 不得解释为论文性能复现完成 |
| 论文数值对齐 | BLOCKED | 私有DRAM/EDA/调度细节缺失 | 作者artifact或明确独立重建 |

## 阶段 0 验收

- [x] 完整读取并视觉核对 `TODOLIST(1).docx` 的7页内容。
- [x] 冻结HiBand准确身份。
- [x] 冻结H2-LLM准确身份、官方artifact URL、许可证和远端提交。
- [x] 识别并冻结3D-TANoC准确身份。
- [x] 建立证据与假设账本。
- [x] 建立现有配置来源账本。
- [x] 明确旧36端点与参数模板不能冒充论文配置。
- [ ] 用户确认HighBand是否指HiBand。
- [ ] 用户确认TODOLIST中的TANoC是否指3D-TANoC。
- [ ] 获取并核验3D-TANoC全文。
- [x] 在113服务器完成只读身份/代码盘点。

阶段0核心身份冻结判定为`PASS`；由于仍有未关闭及外部阻断子项，阶段0总体判定为`PARTIAL`，不是完整PASS。

### 未关闭项对阶段1的影响

- `HighBand`/`TANoC`别名确认：阻断以这些别名建立正式复现对象，但不阻断项目双网络规格定义。
- 3D-TANoC全文与代码：阻断3D-TANoC架构/实验复现，不阻断HiBand与项目双网络的阶段1映射。
- HiBand官方代码/RTL：阻断官方实现和精确数值复现，不阻断显式标注假设的独立功能模型设计。
- 113盘点：阻断依赖远端资产的工作，不阻断本地只读规格冻结。

## 下一阶段入口条件

阶段1可以先开展不依赖歧义名称的部分：

1. 定义`project_dual_network`端点、方向、请求/响应、packet/flit和共享资源。
2. 建立HiBand global/local路径与项目Memory-to-Core/Core-to-Core的“不预设等价”映射表。
3. 冻结同构GPU或同构NPU二选一；未选择前不生成架构相关trace。
4. 为现有旧36端点结果统一添加`project_legacy`标签。

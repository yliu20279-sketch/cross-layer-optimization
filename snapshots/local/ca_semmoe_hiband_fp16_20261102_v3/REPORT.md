# P0-1a—P0-1c：Qwen1.5 GPTQ解码FP16续作

日期：2026-11-02。状态：**PARTIAL，权重资产阻断已消除；完整原生组合实现尚未完成。**

## 1. 合同修订

用户授权将现有GPTQ权重离线解码后采用FP16。实际模型为 `Qwen/Qwen1.5-MoE-A2.7B-Chat-GPTQ-Int4` 的解码FP16表示；这不会恢复量化前权重，也不会使Chat变体成为原版基础模型。论文负载名称应明确标注该身份。Qwen3-30B-A3B继续采用原BF16合同。

原版BF16 checkpoint不再作为Qwen1.5本路线的必需资产；不得继续以“未找到原版BF16”为本轮阻断理由。源GPTQ只保留为溯源档案，目标权重读取路径不执行解包。

Qwen1.5目标内容指纹：`af39a579429fbd36a9b6c8507344d07b789d034eec0fb305b294d25bd807120c`。此为本地内容快照身份，不是已核实的上游发布commit。

来源：[Qwen1.5合同](contracts/qwen15.json)、[Qwen3合同](contracts/qwen3.json)、[完整转换元数据](evidence/FP16_COMPLETE_METADATA.json)。

## 2. 已确认完成

| 项目 | 已完成范围 | 验收边界 |
|---|---|---|
| 全投影离线解码 | 4488个GPTQ投影；两种解包公式逐FP16位一致；183个旧投影精确复用、4305个新投影文件 | CPU解码与持久化，未执行完整模型 |
| 完整目标清单 | 4659对象，有效权重字节28,631,568,384 | 不是HF可直接加载checkpoint承诺 |
| 非零bias保留 | 72个Q/K/V bias保留；4416个全零投影bias折叠 | bias消费绑定已生成，尚非全模型数值执行 |
| 去除GPTQ档案运行依赖 | 99个原dense权重及72个bias单独保存FP16；目标仅依赖raw FP16与旧纯FP16文件 | 原GPTQ档案仅溯源保留 |
| 字节服务 | 4659对象实际抽样读取；共享TP片段重组完整SHA一致；独立文件版9318次跨度读取通过 | 抽样跨度不是对所有目标字节的第二次全量重算 |
| EP/TP绑定 | 4992条投影绑定，72个bias有消费者；共享down的rank部分输出FP16，再FP32求和、最终FP16 | 绑定描述，不冒充已运行目标GEMM |
| 原生观察钩子 | 旧完整事务后端源码插入实际成功accept/callback接口，编译链接通过；33个后端对象核SHA | 非Sem-MoE/HiBand完整实现 |
| 事件接口 | C++两事务反序回调，6项拒绝控制；事件可导入Python CoAccess参考 | 接口探针，非模型或系统仿真 |
| 软件检查 | 本地23项通过；113最终implementation_04的23项通过 | 无完整模型、GPU或性能实验 |
| 运行身份 | Qwen1.5候选可执行文件及13项库身份；Qwen3已有BF16运行组件身份核验 | 身份一致不等于组合功能通过 |

来源：[档案脱离回执](evidence/ARCHIVEFREE_METADATA.json)、[字节服务回执](evidence/ASSET_SERVICE_RECEIPT.json)、[投影绑定](contracts/qwen15_projection_bindings.json)、[原生编译回执](evidence/NATIVE_BUILD_RECEIPT.json)、[C++事件导入](evidence/NATIVE_EVENT_IMPORT_CHECK.json)、[113最终软件回执](evidence/SOFTWARE_CHECKS_113_04.json)。

源码哈希核对发现Windows换行导致“生成文本SHA”与实际源码字节SHA不同，已明确区分；本地实际源码字节与113编译来源均为 `96b5d78f967898fbfb7a40a5c6bb2d4a1562ce2b98778dcb291fdbd6472c37ba`。没有将不同哈希解释为相同文件。[来源](evidence/NATIVE_HOOK_SOURCE.json)

## 3. P0分项结论

P0-1a：两模型身份、精度、权重来源与运行候选身份已具体化；Qwen1.5权重缺项解除。完整激活/KV/SRAM/HB驻留与回收、时序成本仍未认证，因此不能写“完整合同验收通过”。

P0-1b：参考算法、数据服务、投影绑定与候选钩子已经实现并做有限检查；完整原生调度与数据通路仍未接通。源码准入仍为false。

P0-1c：本轮复用分类已更新。可复用183个逐位相同投影、旧layer0有限数值结果及后端源码/构建身份；不能复用旧W4代理周期为新FP16组合收益，也不能将旧Qwen3 FP16结果替代当前BF16合同。已有GPU GPTQ轨迹若用于新目标的自主路由结论，需要重新验证目标执行一致性。

来源：[复用决策](evidence/REUSE_DECISIONS_v3.json)、[113实际路径最终准入](evidence/REMOTE_GATES_final.json)、[实现清单](IMPLEMENTATION_STATUS.csv)。

## 4. 剩余实现与验收条件

以下是未完成工作，不是本轮已通过结果。保持原计划，不启动P0-2或正式性能矩阵。

| 顺序 / ID | 修改位置 | 必须补齐 | 完成标准 |
|---|---|---|---|
| 1 / Q3-02、Q15-03 | `models/*/build_graph.py`、真实目标入口 | 将参考图、router、专家、shared、attention与目标执行连接；Qwen1.5保留72个bias及既定FP16边界 | 有完整调用链、输入输出/布局绑定和失败传播；不得仅返回图描述 |
| 2 / Q3-03 | `core/collectives.py`、目标通信适配 | SRS/SAG实际载荷、槽位恢复、all-peer通信与计算依赖 | 路由token身份与字节守恒接入真实执行，含反向回传；参考置换通过不代替目标接入 |
| 3 / Q3-04 | `core/artifacts.py`、BF16原生读取入口 | 将现有Qwen3 BF16权重与真实算子读写绑定；禁止按FP16重解释 | 真实读取dtype、地址、有效字节、依赖和输出绑定可审计 |
| 4 / C-01 | `runtime/native_main_fp16_hook.cc`及两模型入口 | 完整Sem-MoE调度与真实payload连接；现有钩子只观测事务 | 真实请求产生accept/callback并关联正确对象/代际；覆盖prefill/decode路径 |
| 5 / C-04 | `core/runtime.py`、真实HiBand控制入口 | drain、切换、域预算、驻留、缓存版本和目标时间成本接入 | 实际控制路径执行，失败显式传播，开销不为未解释的0/null |
| 6 / C-05 | `runtime/p0_event_sink.h`、真实地址分配器 | CA页映射落到目标实际地址，补动态generation与生命周期 | 映射双射、固定页不动、越界拒绝、回收后旧代际拒绝；CPU/传输/维护成本覆盖且不重计 |
| 7 / 两模型公共 | `contracts/`与能力证据 | 补HB/KV/activation/SRAM峰值及持续生命周期、CPU/PCIe/缓存服务成本 | 独立证据及其SHA齐全；源码完成与P0-2实证验收分开记录 |

当前源码缺项：Qwen3为Q3-02/03/04及C-01/04/05；Qwen1.5为Q15-03及C-01/04/05。113最终只读核验已消除本地无法访问Linux路径造成的假“运行文件缺失”；真实缺项仍存在，两模型performance_ready均false。[来源](evidence/REMOTE_GATES_final.json)

## 5. 存储与复现入口

113资产：`/mnt/sda1/h3240101068/ca_semmoe_hiband_fp16_20261102_v3/decoded_assets`。活跃目标为 `TARGET_MANIFEST_ARCHIVEFREE.json`，文件SHA为 `49a5568584285eba9675c770356ba2d7f13412a01124d21c0478b1124861bc21`；原TARGET_MANIFEST保留为历史中间版本。

最终代码与合同：113同根目录 `implementation_04`。`implementation_02`的共享部分输出描述为早期中间版本，不能作为最终数学合同；最终采用FP16部分输出、FP32归约、FP16结果。implementation_03是修订前的过渡包，04为最终交付版本。

本地及D盘只交付代码、合同、清单、检查回执与报告，不包含约28.6GB目标权重。历史失败与旧版本保留。没有启动P0-2、完整模型前向、GPU或新性能比较。

已有结果原始来源：[旧FP16物化报告](../selector_real_fp16_materialize_v1/REPORT.md)、[旧原生联合后端报告](../selector_fp16_joint_native_v1/REPORT.md)、[Qwen3 FP16边界报告](../selector_all_moe_formula_v1/TARGET_FP16_REPORT.md)。D盘副本内这些相对链接不指向项目目录，请使用同目录SOURCE_LINKS.md中的绝对来源链接。

# swe_qwen3 步骤3诊断与开发验收

2026-10-26。整体仍为 PARTIAL_AGENT_NOT_READY；原BF16 GPU参考后端、真实路由与fixture采集已建立，两项开发任务未修复，留出未运行。不能升级为benchmark就绪、目标NPU执行或HiBand/Sem-MoE收益通过。

## 结论与适用范围

不是单一原因。确认存在本地适配/评测缺陷，也确认模型在当前非thinking文本工具策略下重复错误动作、反复查找示例类、未推进实现修改。普通报错确实进入上下文，不能把原停滞全部解释为反馈丢失；也没有证据证明BF16权重错误或模型整体不会写代码。

单轮对照中，同一原BF16模型在greedy与采样两配置下都生成了正确mean函数，三项断言均通过。这只支持该简单函数的单轮生成能力，不是SWE任务、稳定自主修复或模型总体能力认证。来源：[单轮对照](diagnostic_followup/DIRECT_CODE_CONTRAST.json)。

## 已修正与核查

1. 原工具模板漏exception_info，已补齐；stdout、异常说明、退出码哨兵回归通过。原sed报错本来在stdout/output中可见，故不是原错误循环的直接解释。
2. v2简化提示后模型输出标准bash围栏，解析器只接受自定义标签，三次动作被拒绝。v3统一提示与官方可配置正则为bash，真实旧响应回归通过。官方DefaultAgent与解析函数源码未改。
3. 采用官方非thinking采样建议temperature0.7、top-p0.8、top-k20；提示改为简短通用工作流，未给实现答案。官方建议不是成功保证；greedy与提示偏置的贡献未被独立统计分离。[官方模型卡](https://huggingface.co/Qwen/Qwen3-30B-A3B#best-practices)。
4. v3把上下文扩到32K却未先验证整段eager预填充显存，这是本轮配置遗漏，开发任务实际OOM。v4改256-token分块预填充＋expandable_segments allocator，不截断历史，不改原BF16权重或原eager数学函数；同一1903-token上下文整段/分块生成token一致，CPU小配置17/32/33三边界缓存API检查通过。这不是全部输入逐层数值认证。
5. 分块后正确记录所有prefill块、每个forward真实48层expert IDs/最终BF16权重；第0层保存各prefill块与首decode前KV。phase按原prompt边界划分，不能把后续prefill块算成decode。
6. 旧评测venv的默认python残留指向3.8，依赖实际装在3.11，改用明确python3.11。旧镜像git不支持--allow-empty，非空补丁用git apply --verbose，空补丁不执行apply；固定官方v3测试脚本与评分函数未改。
7. 原git diff可能漏暂存或未跟踪新文件。停止后的自有容器按登记base_commit收集完整最终文件树差异，保留原diff；只改变git intent元数据，不修改实现/测试内容。
8. 通用环境约束拒绝相同文件状态下的重复失败动作，识别“|| true”使退出码0但仍有Python Traceback的情况；保留真实退出码并明确提示。已有测试被保护，拒绝/还原事件单列。CPU容器回归通过。这是有约束的agent变体，不是作者未改默认agent配置。

两项actor shell环境另做核对：默认python和显式testbed python均正确指向testbed环境，均导入登记源码；没有发现actor解释器混用。来源：[环境检查](ACTOR_ENVIRONMENT_AUDIT.json)。

## 两项开发任务：官方评分0/2，不能算总体成功率

| 登记任务 | agent退出 | 最终完整补丁 | 官方目标测试 | 原回归测试 |
|---|---|---:|---|---|
| marshmallow-code__marshmallow-1359 | 重复语法错误动作，三次相同拒绝后受控停止；未跑满预算 | 0 B | 0成功／1失败，resolved=false | 76通过／0失败 |
| marshmallow-code__marshmallow-1343 | TimeExceeded；45分钟为轮间检查，实际可被当前生成超出 | 0 B | 0成功／1失败，resolved=false | 24通过／0失败 |

来源：[官方评分](OFFICIAL_EVALUATION.json)、[完整补丁审计](PATCH_CONTRACT_AUDIT.json)。首次失败表现为把class复合语句放进不合法的单行Python命令；另一项持续寻找问题描述里的类/方法名、反复读取测试文件，未产生实现修改。没有手工代修或把后续单轮函数诊断替换为开发成功。

正式开发记录29次model.generate请求、1759个生成token（含实际结束token）、121872份layer-forward路由记录；这些记录不是独立任务样本。全部已完成请求的成员SHA、48层路由覆盖、Top8范围/权重dtype、prefill token总数、decode次数及KV长度检查通过，无未完成请求目录。来源：[采集审计](CAPTURE_AUDIT.json)。这不等于完整层/两层数值验收。

最长真实开发prompt为18213 tokens，峰值allocated 64686345216 B、reserved 65200455680 B，分块路径未再OOM。此观察不认证完整32K容量或所有输入数值等价。来源：[容量回执](diagnostic_followup/CAPACITY_RESULT.json)。GPU时间为带采集的参考后端功能时间，不是目标NPU周期或生产吞吐。低吞吐与轮间时间预算也限制可尝试回合，超时不能当作纯模型能力上限。

## 所有尝试与未解决项

v1原失败、v2格式失败、v3小仓库提交/两项原测试通过与随后OOM、v4不同seed序列的小仓库失败、v5失败均保留；各版本提示/采样/后端不同，不能据1次通过与多次失败计算成功率。v6不再反复重抽tiny直至成功，利用已证明的基本交互闭环观察两项开发结果，明确模型策略稳定性未过。分阶段来源见证据包内diagnosis_receipts与DIAGNOSIS_RECEIPTS.json。

已确认普通工具反馈和基本执行链可用；仍未完成对提示、非thinking模式、工具协议与模型固有能力的全部因果分离。当前配置不宜进入策略收益实验。后续应另立开发协议比较推理/原生工具调用策略，而不是把当前0/2外推成总体模型结论。

两项留出仅登记身份，问题正文/gold未进入agent。自动审批拒绝了“冻结后读取问题正文”的拟议动作，理由是旧协议限制为仅读留出ID；没有绕过。[未放行范围及具体两项ID](HOLDOUT_BOUNDARY.json)。

## 交付与下一道门槛

远端：/mnt/sda1/h3240101068/swe_qwen3_step3_development_20261026_v6。机器状态[已授权开发工作收尾](AUTHORIZED_COMPLETION.json)只表示两项开发观测、评分、诊断与证据工作完成，整体步骤3仍PARTIAL。

EVIDENCE.tar.gz含真实路由/第0层fixture、请求token/消息、工具日志、各版本诊断回执、官方测试/评分及实际驱动；不含再次复制的61GB模型权重。包3076790615 B、276载荷文件4269140217 B，本地外层及全部载荷SHA核验通过，见[本地回执](LOCAL_EVIDENCE_VERIFICATION.json)。本地只验证字节完整性，数值/结构检查来自远端独立审计；本报告为包外结论说明。

固定host128 GiB＋HB8 GiB及原BF16约束不变；GPU物理显存不等于目标HB容量。NPU仿真0，未认证完整层数值、目标BF16吞吐、分页/NoC/时序或策略净收益。真实fixture已可供步骤4独立核查；当前失败不允许把步骤3写成整体PASS。

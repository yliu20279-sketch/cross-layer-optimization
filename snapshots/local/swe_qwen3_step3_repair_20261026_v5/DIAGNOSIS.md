# swe_qwen3 自主修复停滞诊断

本轮保留v1原失败、v2格式失败、v3 OOM/受控中断、v4另一随机序列的小仓库失败。它们不是独立留出，也不能只挑v3成功计修复率。

## 可以确认

原普通工具反馈没有丢失：v1 R0010的消息中有退出码1、Traceback和sed报错，模型也承认过错误。v2在同一1903-token失败上下文中，采集开/关生成token一致，限制排除了该输入上观察插桩导致重复的解释。见../swe_qwen3_step3_repair_20261026_v3/CAPTURE_EQUIVALENCE.json。

原观察模板确实遗漏exception_info，已按官方默认模板补齐。原sed报错本来在output中可见，因此该潜在缺陷不直接解释原错误循环。真实旧响应回归也确认，v2简化提示后模型输出bash围栏、解析器却只认mswea_bash_command，动作被拒绝；v3统一为标准bash，使用同一官方可配置正则解析函数，回归通过。见../swe_qwen3_step3_repair_20261026_v3/ADAPTER_REGRESSION.json。

模型决策仍有问题：v3小仓库自主提交并通过两项原测试，v4同精度/相同通用提示在另一请求seed序列上再次生成错误修改并重复sed失败。因此不能声称仅修改采样或格式就完全解决，也没有证据把问题解释为BF16权重错误。v1/v4失败均保留。

v3开发任务的OOM是后端容量问题，不能算模型解题失败。将上下文上限扩大到32K之前未验证eager attention峰值是本轮配置遗漏；v4改为256-token分块预填充，不截断历史、不改原BF16权重或原eager数学函数。原模型1903-token上下文整段/分块生成token一致；CPU小配置17/32/33三边界API检查通过。此有限对照不等于所有输入逐层数值等价。见../swe_qwen3_step3_repair_20261026_v4/PREFILL_EQUIVALENCE.json与CHUNK_CACHE_CPU_CHECK.json。

评测准备也存在独立问题：旧eval_venv残留python指向3.8，依赖装在3.11，改为明确python3.11；旧镜像git不认--allow-empty，非空补丁改为git apply --verbose，空补丁基线不执行apply。两项开发基线已正常官方评分，原失败日志保留于v2。

原git diff补丁提取可能漏掉已暂存或未跟踪新文件。新版collect_patches.py在停止后的自有容器中，仅设置git intent-to-add并相对登记base_commit导出完整最终文件树差异，不改实现/测试内容；原patch仍保留，官方评分明确用predictions_complete.jsonl。

## v5通用约束

提示优先使用Python脚本编辑Python、阅读原测试、使用已安装工具，不给任务答案。同一文件字节状态下重复执行已失败命令会被拒绝；开发任务修改已有测试会被还原并返回违规反馈，tiny原测试文件以只读bind mount保护。实现源码只能由模型动作修改。原工具输出、拒绝及还原事件分别保存，不能把被约束还原的违规动作说成模型从未尝试修改测试。

独立CPU容器check_guards.py验证重复失败拒绝、已有测试还原与最终test diff为空，CUDA未初始化。实际任务结果仍以TINY_RESULT、任务RESULT、PATCH_CONTRACT_AUDIT及官方测试报告为准。

## 推测与未验证

greedy、长sed示例可能共同促成v1重复；v2单次采样改变了命令，但没有独立随机多次实验分离各贡献。官方非thinking采样建议为temperature0.7/top-p0.8/top-k20，已采用，来源：https://huggingface.co/Qwen/Qwen3-30B-A3B#best-practices 。官方关于greedy无限重复的明确警告针对thinking，不能偷换为旧nonthinking失败的因果证据。

真实SWE能力、所有随机序列稳定性与目标NPU语义/时序尚不能从小仓库推断。本轮没有训练、量化、FP16模型替换、目标仿真或策略收益认证。留出仍仅读ID，问题正文读取被自动审批拒绝；未绕过，见../swe_qwen3_step3_repair_20261026_v3/HOLDOUT_BOUNDARY.json。

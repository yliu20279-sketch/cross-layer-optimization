# swe_qwen3 步骤3：冻结留出结果与交付

核验/交付日期：2026-10-27，Asia/Shanghai。步骤3的预定GPU采集、两开发＋两留出运行和官方评分工作已完成；当前agent方法未通过任务修复准入，不能将整套复现记为PASS。

## 冻结、授权和信息隔离

用户明确批准“方法冻结后读取两项留出任务的问题正文，gold和隐藏测试继续隔离”。[授权修订](AUTHORIZATION_AMENDMENT.json)已解除此前同一读取范围的拒绝，旧拒绝仍是历史，不是当前阻断。

最终[FREEZE.json](FREEZE.json)于2026-10-26 UTC12:57:24（北京时间20:57:24）落盘，绑定17个方法/协议文件。读取正文前发现监视器可能早于基提交复位记录状态，保留旧冻结与旧代码，完成预访问修订再重新冻结；这发生在任何正文读取前，未依据模型结果改方法。

[PROBLEM_ACCESS.json](PROBLEM_ACCESS.json)记录正文访问UTC13:02:11（北京时间21:02:11），晚于最终冻结。仅筛选已登记的Astropy-12907/14182，actor列为instance_id、repo、base_commit、problem_statement、version；gold的patch列未读取。隐藏test_patch和测试集合仅由所有生成结束后的独立评测进程读取，未挂载进actor容器、未加入模型消息。

模型仍为原Qwen3-30B-A3B BF16，非thinking、temperature0.7/top-p0.8/top-k20、逐请求种子20261026＋计数器；256-token分块prefill、32K上下文不截断历史、工具输出12K字符显式裁剪。每任务50轮/2700秒轮间门控，单轮生成可使实际退出晚于45分钟。原失败动作及空搜索停止规则在访问正文前固定，留出中没有调参、追加重试或手工修补。

Astropy测试位于多个子目录，已有测试保护在读取正文前适配为全部*/tests/*，与Marshmallow开发期根tests目录的布局不同；此为预先声明的仓库适配，不能声称与开发期代码逐字相同。提示和推理参数未变。

运行后[FROZEN_METHOD_VERIFICATION.json](FROZEN_METHOD_VERIFICATION.json)确认17文件哈希仍一致。镜像归档SHA与Docker image ID已校验，见[IMAGE_VERIFICATION.json](IMAGE_VERIFICATION.json)。

## 官方留出结果：0/2，不是总体成功率

| 实例 | agent退出 | 最终完整补丁 | 官方FAIL_TO_PASS | 官方PASS_TO_PASS | resolved |
|---|---|---:|---|---|---|
| astropy__astropy-12907 | TimeExceeded | 0 B | 0成功／2失败 | 13通过／0失败 | false |
| astropy__astropy-14182 | 三次相同失败动作拒绝后受控停滞停止，未跑满预算 | 0 B | 0成功／1失败 | 9通过／0失败 | false |

来源：[OFFICIAL_EVALUATION.json](OFFICIAL_EVALUATION.json)、[PATCH_CONTRACT_AUDIT.json](PATCH_CONTRACT_AUDIT.json)。官方v3测试脚本与评分函数通过独立wrapper执行，未冒称调用了完整上游CLI。空补丁没有实际修复内容，harness补丁/日志处理标志不能代替resolved。

12907持续重复输出嵌套模型的separability矩阵而未修改实现；14182复现RST写出错误后重复失败动作，触发预先固定的停止条件。两个最终文件树均无实现/测试修改，也无遗漏的暂存或未跟踪新文件。完整补丁相对登记base_commit导出；采集器仅设置git intent元数据，不代修源码。

此前两开发任务同样0/2、空补丁，见[开发报告](../swe_qwen3_step3_development_20261026_v6/REPORT.md)。合计4个预登记pilot实例均未修复；实例少且来自公开SWE-bench，不能据此估计总体成功率、宣称模型训练未见或归咎BF16精度。旧小仓库曾有一次自主提交通过，单轮mean生成也曾通过，均不替代真实SWE任务通过。

## 真实采集与有限验收

本轮46次完整model.generate请求：12907为30次、14182为16次；3188个生成token含实际结束token，172992份layer-forward路由记录，不是独立任务样本。最大prompt4079，峰值allocated61883108352 B。来源：[CAPTURE_AUDIT.json](CAPTURE_AUDIT.json)。

独立审计通过所有已完成请求成员SHA、每forward的48层路由覆盖、Top8范围/最终BF16权重、prefill/decode计数、首decode第0层KV长度及fixture dtype；无未完成请求目录。保存每块prefill和首decode的第0层输入输出、必要FP32中间值与同checkpoint权重引用。不重新计算普通TopK冒充真实dispatch。此为字节/结构验收，不是完整层/两层数值等价或目标设备认证。

方法期间未出现新OOM；此前开发真实18213-token请求的容量证据另保留于开发目录，不能由本轮4079-token上限外推32K完全认证。GPU wall/CUDA事件为带采集的参考功能时间，不是目标NPU周期或生产推理吞吐；参考后端速度与轮间墙钟预算也影响可尝试轮数。

官方harness版本标识纠正：670fb056fc68105fdcd3c6b71dae618778f14b86是v3.0.0注释标签对象，实际提交为d83e1001739f4d96add351d9ec0d56f4594a0d82。继承的BINDING字段把标签对象叫harness_commit，按[源身份纠正回执](HARNESS_SOURCE_ATTESTATION.json)解释；代码与版本未更换，Git工作区干净。

## 交付与结论

远端：/mnt/sda1/h3240101068/swe_qwen3_step3_holdout_20261026_v1。EVIDENCE.tar.gz包含冻结、授权、输入边界、真实路由/fixture、全部请求/工具日志、完整补丁、官方测试和实际方法代码；不重复打包模型权重及Docker镜像。包1561380291 B，307载荷文件2244957134 B，本地外层及全部载荷SHA通过，见[本地核验](LOCAL_EVIDENCE_VERIFICATION.json)；本地只验证字节，不重复声称数值认证。本报告为包外结论。

固定128 GiB host＋8 GiB HB与原BF16约束未改，物理GPU显存不是目标HB容量。NPU运行0；未认证目标BF16吞吐、完整层数值、分页/NoC/时序或HiBand/Sem-MoE净收益。

结论：STEP3_EVIDENCE_EXECUTION_COMPLETE_FUNCTIONAL_ADMISSION_FAILED。当前固定agent方法不应作为已跑通的SWE复现基线。若后续修改推理或工具策略，应回到开发，并重新登记尚未读取的新留出；本轮两项已使用，不能继续冒称未见留出。现有真实fixture可供步骤4独立数值核查，但不能把当前失败轨迹性能写成成功任务收益。

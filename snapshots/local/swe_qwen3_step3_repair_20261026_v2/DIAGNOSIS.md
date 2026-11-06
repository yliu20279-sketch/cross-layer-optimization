# 小仓库停滞诊断与步骤3修复

原始失败保留于../swe_qwen3_step3_gpu_20261026_v1/，本目录新建协议与结果，不覆盖原补丁/日志/回执。

## 已核实的静态事实

原R0010/messages.json包含前两次sed失败的退出码1与完整报错；Traceback、当前错误表达式也曾进入模型历史。模型输出有承认错误的文字，却重复原命令。因此没有证据表明这些普通工具反馈丢失，失败发生在模型选择下一条命令的环节。官方actions_text.py的格式化函数与自定义LocalModel调用签名一致，模型消息角色及顺序符合该文本模式。

原后端明确覆盖checkpoint采样配置，使用do_sample=False/greedy，关闭thinking；官方对非thinking建议temperature0.7/top_p0.8/top_k20（https://huggingface.co/Qwen/Qwen3-30B-A3B#best-practices）。这属于运行配置偏离建议，不能直接证明它是唯一原因。官方关于greedy无限重复的明确警告针对thinking模式，不能把该警告偷换成对旧nonthinking运行的直接因果证明。

原default提示包含多条sed示例且要求较长解释，模型随后沿用sed。可能有提示偏置，但没有独立统计证据。本轮将其替换为通用、简短、读反馈后行动的协议；不注入mean修复代码、错误命令的正确替代或SWE答案。

原观察模板省略exception_info，与官方默认模板不同，可能隐藏超时等异常，属于潜在适配缺陷。已补齐并用stdout/异常/exit9哨兵核对。旧sed错误在output字段已可见，故此缺陷不解释该次重复。见FEEDBACK_AUDIT.json。

## 有界GPU对照（结果以回执为准）

同一旧R0010消息，原greedy采集关闭/开启，各max128，核对生成token；随后同一旧消息改用官方nonthinking采样。只生成诊断输出，不执行其命令。采集开关相同可限制排除观察插桩改变生成，但不能认证所有输入或逐层数值。

单次采样对照与新提示小仓库重跑只能证明这一配置下的有限行为变化，不能严格分离提示、采样、随机seed的全部贡献，也不能断言模型固有能力无问题。下一步不修改原权重、BF16精度或eager源码。

## 评测适配排查

旧eval_venv先由系统Python3.8失败创建，再由Python3.11重建，残留bin/python指向系统3.8，但pip指向bin/python3.11。依赖实际安装于3.11；本轮显式使用eval_venv/bin/python3.11，旧ModuleNotFoundError日志保留。这不影响原GPUvenv，也不解释原小仓库错误。

官方旧镜像git不支持--allow-empty；wrapper改为非空补丁用git apply --verbose、空补丁基线不执行apply。测试脚本与评分函数仍来自固定官方v3源码。原失败日志、第一次空补丁错误目录保留，修正基线写baseline_evaluation_v2。基线与隐藏测试不反馈给agent；不读取gold patch。

## 协议

见PROTOCOL.json：新建小仓库、相同原测试；提交＋测试通过＋原测试哈希不变才放行。开发使用两项先登记任务，所有失败保留；不把小样本计为总体成功率。真实路由和第0层fixture继续采集，GPU功能与目标NPU时序分开。

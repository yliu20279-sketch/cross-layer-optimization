# 步骤3 v3预备：实现范围与工具交互

本文件记录准备阶段快照；实际运行/最终结果以STATUS.json、DEVELOPMENT_GATE.json、FINAL_STATUS.json和REPORT.md为准。

候选代码与CPU脚本控制合同已准备；尚未启动GPU。仅v2完整官方评分失败且证据封包后才允许自动启动一次两开发候选，v2通过则跳过，不终止/移动/覆盖v2。

v2开发轨迹已经观察到：模型把库修复当作调用示例的规避，反复修改新复现脚本；thinking有一次最终答复输出两个bash块被单块规则正确拒绝。此为开发观察，不读取新留出或gold，也不据此改正在运行的v2方法。

预备改动：明确库维护者角色，保持问题示例输入与语义；给实际git源文件/解释器清单以避免猜site-packages路径；按包实现差异计进展，复现脚本不计；成功且无文件变化的纯检查命令缓存；最终答复允许一至两个有序bash块，前块失败即跳过后块。新方法须在已用开发重新验收，通过后另冻结才读取尚未使用的新留出。

固定原BF16及host128/HB8，NPU运行0。不手工代修模型补丁，不给库修复答案，不声称未运行分支有效。来源：v2的FINAL_FORMAT_DIAGNOSTIC.json、各任务EVENTS.json及COMPLETE_PATCH.diff。

CPU脚本合同通过实际容器验证目录引导、缓存检查不重执行、复现不算库进展、无库补丁拒绝提交、前块失败跳过后块和完整补丁收集；模型生成0次，不能当Qwen/SWE成功。真实GPU仍须独立开发官方评分。见远端CONTROLLER_CONTRACT_TEST.json。预算及一次性停止边界见PROTOCOL.json。

预GPU修订：v2最后一项首请求4096-token截断且未结束thinking，候选单轮上限改8192，总32768-token/5400秒轮间预算不变；容器240分钟仅兜底长生成后的收尾，不增加任务预算。旧封存/源码保留于candidate_history，详见PRE_GPU_AMENDMENT.json。两镜像规范归档位于v2远端目录及本地v2目录，不在v3重复复制；新留出前再次实时复核Docker image ID。

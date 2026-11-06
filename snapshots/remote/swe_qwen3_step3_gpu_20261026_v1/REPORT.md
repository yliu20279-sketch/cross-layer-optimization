# swe_qwen3 步骤3：原BF16 GPU基准与真实采集

2026-10-26。状态：PARTIAL_GPU_CAPTURE_PASS_TINY_REPAIR_FAILED。步骤3未整体通过。

## 已确认

113的H100 PCIe GPU0加载原Qwen3-30B-A3B，30,532,122,624参数全部BF16；未量化、未替换FP16、未训练、未调用外部模型API。torch2.6.0+cu124、Transformers4.51.3/eager，冻结官方模型源码SHA一致。加载308.50秒，记录最大allocated约61.06GB。见GPU_BACKEND_BINDING.json。

短生成采集关闭/开启均返回READY，生成token逐项一致。单对5.728/2.234秒有冷启动/顺序混杂，不能据此判断采集开销或速度收益。见SHORT_GENERATION.json。

实际运行官方mini-SWE-agent 2.4.6的DefaultAgent、动作解析和Docker环境；只替换Model接口为本地BF16后端。共12次模型请求（短生成2次、小仓库自主生成10次），未用teacher-forced或gold patch。路由采集插在原MLP实际FP32 softmax/TopK及最终BF16归一化结果处，不重新计算TopK。11次开启采集，保存每个forward的48层实际expert IDs/权重，以及首prefill/首decode的第0层输入输出/attention/router中间值；权重以同checkpoint的key、分片SHA绑定，不重复复制。CAPTURE_AUDIT.json重算成员SHA并核对路由数量、Top8、expert范围与BF16类型；这只是结构/文件验收，不是单层数值验收。

## 实际失败

临时mean仓库先复现空输入ZeroDivisionError。模型自主读取、修改、测试并收到真实错误反馈，但产生了错误的条件表达式，随后多次重复含未转义斜杠的sed命令。900秒预算按官方agent轮间检查，实际984.295秒后TimeExceeded，无提交；最终测试exit1，空输入仍错误，普通均值也被破坏。原test_mean.py哈希未变；模型额外创建test_script.py，也被unittest发现并失败。见TINY_RESULT.json、TINY_TOOL_EVENTS.json及原始轨迹。

这是该固定greedy/关闭thinking配置下的单个合成兼容性案例失败，不能推出模型总体能力、BF16语义错误或Sem-MoE/HiBand收益。工具往返存在，但自主修复门槛未过。没有手工修补模型结果、改测试或追加同案调参；未启动两项SWE开发任务，留出仅登记ID，未读其问题/答案。

## 开发评测准备与修订

TASK_REGISTRATION.json固定官方Lite revision 6ec7bb89b9342f664a54a6e0a6ea6501d3437cc2，dev为marshmallow-1343/1359；test仅登记两项Astropy ID。agent输入导出不含gold/test patch。

原固定SWE-bench v5源码要求旧Lite没有的image/eval_script等字段，单独记录HARNESS_COMPATIBILITY_AMENDMENT.json，准备官方v3.0.0 commit670fb056fc68105fdcd3c6b71dae618778f14b86，未改模型/agent/dataset。独立eval_venv离线安装，未修改共享环境。evaluate_development.py使用该官方test_spec.eval_script及get_eval_report，隔离wrapper不冒称运行了官方CLI；尚未运行评测。

两项官方镜像全部压缩层digest及解压diffID已核验，归档传输SHA一致，docker load后config image ID一致。IMAGE_VERIFICATION.json确认登记base commit对象存在，但镜像初始HEAD不同，驱动已加入在新任务容器中显式reset/clean并重验HEAD；不能直接把latest初始HEAD当冻结任务。开发驱动未启动、未验收。

## 交付与边界

远端目录：/mnt/sda1/h3240101068/swe_qwen3_step3_gpu_20261026_v1。原始采集和日志封存GPU_EVIDENCE.tar.gz，单独SHA回执。本地交付核验见LOCAL_EVIDENCE_VERIFICATION.json（生成后生效）。保留失败、停止后的自有容器、源码和隔离环境；GPU进程已退出，未抢占其他进程。

目标host128 GiB＋HB8 GiB及BF16约束保持。NPU模拟运行0，未认证目标BF16吞吐/单层数值/完整任务/分页/策略收益。下一项工作是检查自主循环停滞原因并独立冻结新诊断协议，不能把本次失败重命名PASS；真实fixture可用于步骤4的独立数值核对。

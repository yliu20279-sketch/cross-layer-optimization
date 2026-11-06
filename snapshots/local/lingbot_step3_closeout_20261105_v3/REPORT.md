# 步骤3收尾及一键复跑

范围为example_4 step0/layer0/query0/head0的单次K投影（M1/K2048/N128）。cond和uncond在各自子目录独立执行两遍。首遍生成自己的PopNet延迟，第二遍应用该分支的延迟。每遍核对128个FP32软件参考及128个原GPU BF16元素，并检查CPU返回、参数化PCIe DMA完成、Sniper目录写回确认和NoC最后接收后的消费者启动时刻。

一键命令在113执行，最后参数必须是尚不存在的新目录。

    /mnt/sda1/h3240101068/lingbot_steps1_2_20261027_v1/venv/bin/python /mnt/sda1/h3240101068/lingbot_step3_closeout_20261105_v3/rerun.py /mnt/sda1/h3240101068/lingbot_step3_closeout_NEW

入口使用同目录replay_source中的最终源码和冻结输入，不需要再手工修补网关。依赖现有Sniper、InterChiplet、Ramulator、PopNet和原portable.c，均沿用113环境。每支运行有内部600秒上限，外部750秒上限，审计60秒；任一失败停止并保留现场。cond和uncond总计4遍phase1，20个子进程回执。

主要证据为CLOSEOUT_AUDIT.json，cond及uncond各自的INDEPENDENT_AUDIT.json、RUNTIME_RECEIPT_AUDIT.json、run中的clock/domain/feedback CSV、Sniper cpu.log、DMA回执和case*/N00/GATE.json。源码快照、二进制、配置、输入和结果按包内MANIFEST.json及DELIVERY.json核验。V2为初次独立分支封装运行，V3为最终封装入口的实际复跑。

验收边界仍为PASS_LIMITED。PCIe是V3.6参数化串行queue0模型；没有新增轮询指令和队列争用模型。CPU/写回完成时刻取保守接收端观察，并另核对原始目录写回fs和网关DMA设备时刻。每支第二遍实际使用自身第一遍反馈，未主张反馈收敛。所选query0的cond和uncond输入字节相同，分支绑定及运行目录独立，当前样本不能验证不同输入载荷下的差异。每遍四项延迟负对照是原始真实回执的门控重放。

本次完成原计划步骤3小路径收尾，完整单层及端到端成本仍PARTIAL。原计划后续为CFG合并、scheduler和VAE边界准入。

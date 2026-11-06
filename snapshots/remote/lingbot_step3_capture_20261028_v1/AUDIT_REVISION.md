# 独立审计修订记录

首次审计失败于 actual_timestep_0，原日志和代码分别保留在远端 audit_attempt1.log、AUDIT_EXIT_attempt1.json、audit_capture.py。采集原始数据未更改，FREEZE中的协议/采集hook/runner保持原哈希。

原源码 pipeline_lingbot_video.py 的 _transformer_timestep 先做 FP32 timestep/1000，再转 transformer_dtype（本次BF16），再乘1000并转FP32。scheduler 999因此进入DiT为1000。首版审计直接比较两者，前提错误。audit_capture_revised.py逐操作复用该数值转换核对，不加容差。

同时修复独立审计内部变量名遮蔽：局部期望权重改名expected_weights，保留expected为预登记的路由键集合，避免后续缺记录负对照误引用权重矩阵。没有改变路由、权重、输出或容差门槛。第二次仅CPU审计，不重跑模型。

此修订不是目标算子数值验收。完整目标BF16/时序仍未认证。

第二次审计已通过全部3936路由后停于temb编码dtype断言：实际原层输入temb为BF16，审计错误地限定FP32（源码在进入block前已有cast）。第三版按fixture的原dtype允许BF16/FP32，finite且无零仍是必需条件，两种格式的非零有限值均无正负零歧义。BF16不转FP32保存；不修改原载荷。原第二版代码/日志保留。

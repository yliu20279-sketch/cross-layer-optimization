# 最小实验协议（可审查草案，未执行）

目的：验证固定基础MoE的真实TI2V和实际路由可采集性。不是证明换应用带来HiBand、Sem-MoE、Bank、NoC或热收益。
版本固定见SOURCE_MANIFEST；不使用DMD学生、不使用refiner、不调用额外27B rewriter。直接采用源码自带 assets/cases/ti2v/example_4/prompt.json 与 first_frame.png，二者本地副本及哈希已保存。原始样例作为开发输入，不能后来称独立留出集。

阶段0（下一步只读）：恢复SSH别名，检查指定缓存目录、Python/Conda环境、两卡拓扑、CUDA compat库与精确包版本；测量模型所有必需组件大小、磁盘余量及加载方式，不递归服务器，不触碰其他作业。
阶段1：新建独立环境，先验证导入、BF16、torch._grouped_mm、attention backend、NCCL/FSDP基本兼容；不修改共享驱动和旧环境。若需要不同torch/backend则追加修订并记录差异。执行前冻结资源预算及组件下载清单；不直接snapshot整个含refiner仓库。
阶段2：基础TI2V单样本单seed42，BF16 DiT/文本编码器、FP32 VAE、diffusers、guidance3、shift3、无refiner。正式参考沿用官方480×832、40步；帧数必须从runner真实解析值显式冻结，不能从pipeline默认81或T2V报告121猜测。单/双GPU拓扑由阶段0/1确定，当前未冻结。先短去噪诊断（1步）只判断加载/forward/采集，不作视频质量、常规路由分布或性能证据；成功后才执行一次完整40步。OOM或依赖失败保存现场并停止，不自动网格搜索、量化或增加卡数。运行预算和拓扑未冻结前不启动。

采集：LingBotVideoRouter.forward实际返回(top_indices,top_scores,logits,scores,scores_for_choice)。直接hook前两项，不重算普通topk。该路由sigmoid+correction bias用于选择、分组候选，聚合分数来自未加偏置scores。特别注意MoE.forward在padding_mask存在时再次屏蔽/归一化top_scores：同时保存router原输出和实际dispatch前权重，不能把前者直接称有效发送权重。
每份分片绑定run_id、样本/图像/文本哈希、seed、scheduler/timestep/去噪索引、CFG条件/无条件分支、层号/模块名、rank/world_size及CP/FSDP组、batch身份、token局部/全局索引与视觉(t,h,w)映射、padding掩码、expert ID、原始权重和实际dispatch权重/dtype、backend、shard/序号及同步边界。共享专家单列，不冒充第129个routed选择。不能用flatten偏移猜全局视觉位置；须从实际patchify/分片路径绑定。
验收：ID在0..127、每真实token8项且无重复、有限非负权重；非padding权重和在BF16误差下符合route_scale2.5；padding按实际dispatch零权重检查。按实际forward计数核对层/步/CFG/rank覆盖，检测丢片重复，不能预设40×48就是调用数。保存原输入、环境、命令、stdout/stderr、退出码、模型分片内容SHA、输出视频及解码帧数/尺寸、路由清单与SHA。
采集开关前后配对运行只在可用资源和预算内执行，比较同输入seed的数值/输出差异，分别报告trace大小、采集时长和无采集性能；hook同步开销不得算模型原始性能。未完成配对时不宣称无扰动或性能。
路由采集不等于算子回放；回放不等于耦合仿真；GPU时长不等于目标架构周期。后续HiBand/Sem-MoE必须另外建立expert→partition、容量与量化/驻留账本、通信依赖及迁移成本；Bank须有原地址和事务，NoC须有真实分片/collective，热须有活动轨迹与合法动作及成本。原始布局、RR、Heat、CA与匹配随机的合同另冻；未完成前NO_PERFORMANCE_CLAIM。

# swe_qwen3 步骤3：进展恢复开发对照 v2

2026-10-27。用户授权修改agent并继续步骤3。当前开发运行中，功能尚未准入；旧失败与留出不覆盖。原BF16、128 GiB host＋8 GiB HB不变，NPU运行0。

修改包括周期性证据/根因/下一步进展检查、停滞后重规划、thinking最终答复解析。思考结束标记按原始token151668定位，只解析最终答复中的唯一bash块；思考仅保存在原始请求，不回填历史。两配置相同轮数/token/墙钟预算，采用各模式官方采样参数，是配置包对照，不能声称独立thinking因果效应。

v1首个202-token开发请求耗时200.245秒，停止后保留完整/部分轨迹并记录INTERRUPTION.json。只读源码定位发现每层原MoE遍历128专家，含大量空专家操作。v2仅在内存AST把遍历集合改为按升序排序的实际专家，保留原路由、逐专家运算和累加顺序，不改安装源码/权重。

开发前有限检查通过：真实第0层权重在1/7/257 token合成输入的输出及router logits逐位一致；整模型短greedy生成token和每forward logits逐位一致。短请求原路径14.6659秒、跳过空专家2.9482秒，单对结果不代表总体/任务加速比或NPU性能。原始回执以远端BACKEND_EQUIVALENCE.json为准。

开发关闭路由/fixture大体量复制，保存原始请求/token/工具/补丁；两已登记Marshmallow任务每配置一次。每任务上限32次生成、16384新token、每次4096新token、5400秒轮间门控；不截断历史，完整快照包括暂存和未跟踪文件。现有测试保护。

官方两开发均resolved并通过测试保护/基础设施门槛才选配置；否则不运行新留出、不降门槛。Matplotlib-25442和Django-11099已按身份SHA顺序登记，正文未读；需方法冻结后才允许访问，gold永不读、隐藏测试仅生成全部结束后独立评测。旧两个Astropy留出已使用。

远端：/mnt/sda1/h3240101068/swe_qwen3_step3_progress_20261027_v2。方法见[策略](policy.py)、[驱动](experiment.py)、[后端有限等价检查](validate_backend.py)、[协议](PROTOCOL.json)、[空专家适配说明](BACKEND_ADAPTATION.json)。采样及思考解析来源：[官方模型卡](https://huggingface.co/Qwen/Qwen3-30B-A3B)。

运行补充：实际agent是复用mini-SWE Docker环境的自定义串行进展检查循环，不是未改官方DefaultAgent。拟议的双GPU并行切换被自动审批拒绝（终止/移动在途轨迹及硬编码PID风险），没有执行；继续原串行任务。门控后续流程已启动，开发失败不读新正文，开发通过才新目录冻结/留出/采集/评分/归档。详情见RUNNING_UPDATE.json；仍未获得最终结果。

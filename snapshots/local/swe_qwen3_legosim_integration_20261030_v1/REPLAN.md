# swe_qwen3 接入完整Legosim的重排计划

固定原BF16、host128 GiB＋HB8 GiB、目标GPU0、16 NPU/每个4 MiB SRAM；原规范host8不改。原功能/事件证据全部保留，GPU GEMM与softmax FP32差异继续单列。本计划不以SWE修复成功率作为工具链准入门槛。

1. **先修复并绑定真实统一入口。** 在本隔离目录以build_entry/CMakeLists.txt构建InterChiplet及C协议库，链接已有Boost1.71而非坏掉的旧1.65二进制。只移除入口构建时不必要的CUDA语言要求，不改调度语义。核对源码/二进制/动态依赖SHA，运行帮助及两进程通信smoke。旧运行目录、共享安装不动。
2. **建立BF16线协议和真实存储往返。** 新CPU/NPU workload driver调用InterChiplet真实SEND/RECEIVE/READ/WRITE协议；descriptor显式dtype=3，校验长度、ID、offset和结果校验值。先运行有限BF16全位型和FP32 RNE边界smoke，NPUSim/Ramulator读写回相同字节后CPU检查，PopNet必须实际收到bench并生成delay records。仅codec通过不能晋级GEMM。不能使用现模板128 MiB DRAM代替8 GiB HB或128 GiB host。
3. **绑定V3.6容量与拓扑。** 从当前冻结架构生成CPU gateway、16 NPU/16 HB分区、NoC节点/通道映射；每HB512 MiB、总8 GiB，host128 GiB独立后备。地址空间、32 B DRAM事务、PCIe packet与NoC flit分开核算，-f4只是入口flit选项，不证明内存事务32 B。先N0/CH0子合同，再真实16节点验证；不将子合同结果称TP/EP全系统。
4. **移植现有BF16功能原语到真实workload driver。** 复用已经逐位检查的C GEMM、向量、norm和softmax逻辑，但将其输入/输出与真实tensor payload、HB地址和统一调度事件绑定。明确CPU求值只是功能模型，NPU服务成本逐原语补账；禁止按FP16阵列吞吐给BF16计时。逐tensor保留BF16/FP32混合边界，特别是router/attention FP32 softmax。补齐gather/index_add/Top8、cast、SiLU、KV、layout，不以HOST_FALLBACK_OPS调用数作为完整覆盖证明。
5. **CPU服务也必须进入统一时间。** host codec、SLEEF、控制、metadata、软件fallback要有Sniper ROI/接口及DRAM/PCIe完成依赖。当前SLEEF AVX512依赖不能直接假定适配默认Gainestown/Nehalem CPU模型：先验证ISA与Pin/Sniper支持，再决定兼容软件构建或单列新CPU研究overlay，不偷偷改CPU目标。unknown成本保留null，不作总时序PASS。
6. **在统一入口下逐级数值与因果验收。** 同R0002原权重/fixture：单op→attention/router/专家子链→单层prefill19与cached decode1→连续层0/1；参考仍为独立CPU源码，并同时记录对原GPU的既有差异。检查阶段hash、KV19→20、权重last-reader、HB/SRAM峰值、NoC尾包/metadata/dispatch/commit、所有子进程退出。gold/隐藏测试不访问，无新SWE运行。没有真实payload和完成门控的回放只列时序代理。
7. **最后才做统一反馈与结论收尾。** 先单轮phase1/phase2 smoke，再至少两轮检查delayInfo确实反馈且依赖不提前；区分轮数限制-t和wall timeout。比较同地址/同输入重复身份运行，不盲设反馈收敛。达到前述门槛再标“Legosim完整入口有限用例PASS”；16 NPU映射、全模型、物理性能和HiBand/Sem-MoE收益另验，不能由统一入口启动成功推导。

步骤3本轮的出口应拆为：既有参考采集保留；完整工具链有限prefill/decode功能/因果验收；CPU/链路/算子服务时序验收。前者不能替代后两者，也不因agent未修复而阻塞前两者。未解决GPU GEMM不得隐去；是否作为特定功能出口的允许差异必须在实验前明确，不能事后放宽。

当前启动条件：本地源码/入口构建适配器和拒绝不完整运行的统一launcher已准备；尚未远端构建、尚无统一入口swe运行。完整执行schema及验收项见INTEGRATION_CONTRACT.json。待批准上传源码包后从步骤1执行，而不是继续把独立Python事件桥重命名为完整工具链。

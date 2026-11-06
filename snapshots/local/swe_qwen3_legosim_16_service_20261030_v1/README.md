# swe_qwen3：16节点、host后备与PCIe服务接入

原BF16，128 GiB host＋8 GiB HB；目标GPU0。本目录是隔离续作，旧数值、EOF失败和三端点诊断回放不覆盖。

## 执行与验收范围

先决条件：上一完整连续两层用例的PopNet、CPU双回执、独立审计及归档通过。run_after_pass.py读取其最终回执后才启动；未通过时不运行新的目标用例。

首个规范16节点用例：从R0002的CPU源语义prefill层0路由中，对每个expert_id mod16的owner取第一个实际选中调用，用相应CPU源post_attention_norm token和原专家完整gate权重执行768×2048投影。这里“实际选中”指该CPU源路径，不是声称与原GPU路由一致；原GPU的10槽位差异保留。这是16个真实投影，不是完整分布式层、不是全19-token dispatch，也不是策略收益实验。

实际执行路径：Sniper CPU映射完整16个原checkpoint文件→从映射区读取原BF16权重→显式host DRAM/PCIe服务→独立gateway16→规范17-router NoC→Ni→独立CHi Ramulator→实际HB加载→C源顺序数值/NPUSim vector服务→HB输出→NoC/gateway/PCIe→CPU严格比较。Ni与CHi一一对应，16个服务器各512 MiB，总8 GiB；投影只使用其中小部分容量，不是8 GiB压力测试。

全部16权重分片重新SHA通过，共61066575648 B。host映射容量137438953472 B；对齐后后备extent61074309120 B，另保留131072 B pinned窗口和1 MiB控制预算。实际发送的选中权重来自原文件映射区；CPU源参考输出另存，不能作为设备输出注入。

## 本轮实现

- domain_service.h及隔离InterChiplet：将专用HB RPC、host/PCIe和水平NoC分账；保存全部transport记录，不通过删除事件制造加速。
- 规范图中16个NPU及独立gateway；隔离PopNet显式XY路由，导出289项next-hop表，避免用任意最短路代替XY。
- HB128 B/5周期共享分区串行占用；host DRAM60 ns/12.8 B/ns显式共享代理；PCIe55.04 B/ns每方向及250 ns单向延迟。HB协议header/reply费用是显式研究overlay，固定HB电气延迟未知。
- 16个实际NPU runtime及16个Ramulator进程。原BF16逐字节传输、完整HB权重读回SHA、last-reader→compute→return依赖和CPU回执门控。
- 两轮输出各自保存，逐条记录NoC profile是否应用；第二轮必须消费全部816条反馈，而不是只检查“加载过delay文件”。
- 失败传播、1200秒运行上限和独立审计；若通过，生成远端DELIVERY_STATUS.json与SWE_QWEN3_LEGOSIM_16_SERVICE_REVIEW.tar.gz。

## 尚不能晋级的结论

BF16矩阵数值仍由CPU功能模型求值，NPUSim采用通用FP32 vector服务；codec、完整FP32归约、非线性和逐Bank SRAM成本没有全部lowering。host DRAM是现有Sniper constant-DRAM overlay的研究代理，不是物理校准。HB固定延迟未知，不补造数值。

因此，即使本用例通过，也仅证明16分区真实载荷、CPU后备和PCIe/NoC/HB依赖的有限功能接入；仍须把这些服务接回完整层0/1，再完成全部算子、CPU软件服务、SRAM与完整层反馈验收。第1—7步仍不能标全部完成。原GPU GEMM/softmax FP32差异保持，无新GPU/agent/SWE或隐藏测试访问。

来源：PROTOCOL.json、HOST_BACKING.json、CASES.json、FREEZE.json、EXTERNAL_DEPENDENCIES.json、各case/RESULT与CPU_PASS、domain_service和routing_xy CSV、INDEPENDENT_AUDIT.json；规范来源../whisper_operator_inventory/target_architecture_v3_6/target_architecture_v3_6.yaml、noc_v3_6.gv；CPU代理来源../swe_qwen3_host_boundary_20261027_v1/cpu_overlay.cfg。

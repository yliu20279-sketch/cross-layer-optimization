# swe_qwen3：首个目标原生FP32 router片段

日期：2026-10-27。结论：PASS_LIMITED_NATIVE_FP32_ROUTER_FRAGMENT。首次在本线执行NPUSim/Ramulator原生片段；物理NPU执行仍为0。不是完整BF16 router/层/模型时序认证。

## 固定输入与边界

复用原短请求R0002的层0首decode moe_input[1,2048]、原checkpoint mlp.gate.weight[128,2048]和GPU router_logits[1,128]。fixture SHA及权重所在完整分片SHA与原绑定一致，见attempt2/PRE_RUN_BINDING.json。本轮未改原权重/适配器/模拟器；原BF16、host128 GiB＋HB8 GiB overlay保持。

BF16输入与权重先由原NPUSim codec在host扩展FP32，将展开值作为临时软件工作区预置CH0，再执行FP32 vector乘加，K顺序固定；输出从CH0读取后由host回写BF16。这是BF16模型的局部软件路径，不是转换FP32 checkpoint；但其HB临时工作区和传输载荷确实加倍，已分账，不能按BF16两字节流量描述本片段。

复用原libolmo_native.so、NPUSim scheduler、Ramulator 512MiB CH0/32B事务、4MiB SRAM；仅N0/CH0活跃、串行事件，无MAC/FP16计算。数值由113 CPU执行，NPUSim/Ramulator完成计算/内存代理事件与完成门控，非物理芯片数学执行。源码及二进制SHA见PRE_RUN_BINDING。

## 实际结果

| 检查/资源 | 结果 |
|---|---:|
| FP32实际输出对顺序CPU参考 | 逐位一致 |
| host回写BF16 logits对原GPU记录 | 逐位一致 |
| 原生事件 | 16651 |
| FP32 vector工作量（含128次清零） | 524416 |
| MAC工作量 | 0 |
| HB读取/写入 | 1065472 / 512 B |
| 实际32B DRAM事务 | 33312 |
| SRAM峰值 | 17408 B |
| CH0地址保留峰值 | 1057280 B |
| 片段代理周期 | 250447 |

来源：attempt2/STATUS.json、INDEPENDENT_AUDIT.json、events.jsonl.gz、sram.jsonl.gz。周期只包含展开FP32工作区已准备后的计算/DRAM/SRAM子合同，不包含下面未建模的边界；不能当完整router时延或用于HiBand/Sem-MoE收益比较。

独立审计逐事件检查早于消费者的依赖、串行完成时间、HB地址范围、每次DMA的32B sector集合/事务数和全SRAM分配释放；与原生计数一致。缺失producer（原scheduler及跨调用桥两种）、提前消费、SRAM越界四项负对照均拒绝。没有认证SRAM八Bank仲裁或多NPU消息乱序。

## 尚未计入的成本

原BF16输入/权重528384 B；FP32软件工作区初始预置1056768 B；FP32输出导出512 B。host解码264192元素、回写128元素，目标CPU/ISA转换周期及PCIe/gateway服务均为null，未塞进片段周期或按零成本认证。host128主后备仍保存完整只读BF16，而非完整FP32模型；本轮只占少量临时展开空间，未做全模型HB驻留证明。

本轮只验证GEMM中的FP32乘法/加法与完成门控，不含router softmax、Top8或rsqrt；此前平局与跨backend差异仍未解决。也不含分页、NoC、TP16/EP16、完整层/两层及完整在线SWE任务。没有新增GPU推理、agent重试、新留出正文或gold/隐藏测试访问。

## 启动失败与环境修订

attempt1在原GPU环境导入原生runtime时缺少onnx，发生于初始化模拟器之前；原源码/冻结及空attempt1保留，STARTUP_FAILURE.json记录错误。依赖只读预检后改用原桥历史venv（torch2.6.0+cu124、onnx1.23.2、safetensors0.8.0），算术/输入/标准不变，在attempt2执行；未安装/改共享依赖。运行命令是CUDA_VISIBLE_DEVICES空、timeout300、历史venv/bin/python运行run_fragment_v2.py；退出0。首次本地生成环境修订命令还出现PowerShell/Python引号错误，未写文件，随后用独立prepare_environment_amendment.py生成。

## 下一项

先把host BF16 codec与展开缓冲/搬移边界接入可审计的目标CPU/hostlink服务；在这些成本有依据前继续保留完整BF16时序未认证。独立的下一算子可复用同一完成门控框架，但softmax/Top8/特殊函数不能按泛用16ops/cycle直接填写其完整时延。两层与Sem-MoE/HiBand整体比较仍后置，SWE修复率不作为本片段准入门槛。

来源：PROTOCOL.json、PRE_RUN_FREEZE*.json、run_fragment*.py、audit_fragment.py；原桥../olmoearth_v3_6_integration_20261025_v1/native_bridge.cpp/run_integrated.py；目标规范../whisper_operator_inventory/target_architecture_v3_6/target_architecture_v3_6.yaml；上阶段../swe_qwen3_real_ops_cpu_20261027_v1/REPORT.md。交付完整性见LOCAL_DELIVERY_VERIFICATION.json，不把文件SHA核验当新数值认证。

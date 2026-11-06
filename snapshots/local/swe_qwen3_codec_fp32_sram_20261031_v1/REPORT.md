# CPU软件、FP32 lowering与SRAM Bank续作

2026-10-31。状态：PASS_LIMITED，1—7步整体仍PARTIAL。原模型与持久activation/weight保持BF16，host128 GiB＋HB8 GiB；目标GPU、新外部GPU、SWE/agent及隐藏测试调用均为0。FP32是无损展开及原累加语义所需的临时表示，不是修改模型精度。

## 前置完整两层验收

[完整两层本地独立复核](../swe_qwen3_legosim_16_layers_20261030_v3/LOCAL_COMPLETE_AUDIT.json)已通过。两轮各56阶段、12严格输出/KV、CPU双回传、759矩阵、450远端矩阵、61真实host参数fetch；每轮28316水平PopNet、188439域服务、216755总传输、433510时钟观测。70个子进程状态均为0。第二轮全部水平记录实际使用第一轮反馈。

最终419载荷归档44894716 B，SHA256 `7f3067f3df78c29773f2876cc04ee78fcd3ac7b91e8327a73a128621a88f6728`，本地全成员SHA、两轮原输出/参考及依赖/时钟断言通过。外部工具二进制由113独立审计核SHA，本地不声称重新核了未回传的外部大文件。两轮是同输入反馈重跑，不是独立样本或反馈收敛证明。

## 实际新增：单token专家gate

隔离目录本身对应M1/K2048/N768，真实专家16权重来自原checkpoint，输入来自原冻结路由用例。Sniper CPU在ROI内执行1574912元素的BF16→FP32展开及768元素的FP32→BF16 RNE；原61,066,575,648 B checkpoint的16分片继续真实mmap后备。原BF16数据和FP32临时数据经PCIe/gateway/NoC进入真实512 MiB活动HB分区。其余架构HB不冒充本片段的活动容量。

设备实际从4 MiB SRAM数组读取FP32操作数，按原64路累加和二分归约顺序运行16-lane乘、加和归约。没有用FP16阵列吞吐计BF16计算，也没有把原C GEMM的结果注入实际输出。每轮：1572864乘法、1573632加法、48384归约加法，共202752条原生计算事件/周期；Bank服务433196周期，12次真实权重tile版本，768行last-reader记录。K整除64使尾部零累加可常量折叠，最终加正零保留。

两轮各768个FP32对未改C源逐位一致，768个BF16对原参考逐位一致。每轮148水平PopNet、2452时钟观测，10个子进程退出0；CPU转换字节、HB读回、SRAM访问/计算/返回顺序及反馈逐项核对。见归档内INDEPENDENT_AUDIT.json及[本地独立NumPy复算](LOCAL_NUMERIC_AUDIT.json)。

145载荷6159094 B归档，SHA256 `f3c5933ec352999e48f9a2fb1012ef8e2a459f7228a0cde2df8e91a9f5fe80ca`，[本地成员验收](LOCAL_ARCHIVE_AUDIT.json)通过。

## 继续扩展：真实prefill的完整6-token专家批量

[批量报告](../swe_qwen3_codec_prefill_sram_20261031_v2/REPORT.md)。使用原prefill中专家16收到的全部token `[0,2,11,14,16,18]`，不是复制单token凑batch。K块768/768/512、块内奇数后偶数、块间顺序与未改CPU源一致。新核两轮各4608个FP32/BF16均严格一致；不能以本单专家通过代替完整19-token层的全部lowering通过。

## SRAM研究配置与失败记录

原V3.6规范只确认4 MiB、8 Bank、总带宽256 B/cycle，未查到端口或地址映射。因此显式采用32 B条带、`bank=(address/32)%8`、每Bank一个共享读写端口作为研究点，原规范不改。读写实际经过资源预约推进runtime时钟；Bank冲突会延后数据使用，不是离线追加总数。同步串行基线未证明流水重叠或异步释放。

每个新核均完成3项冲突挑战：同Bank两请求2周期、异Bank两请求1周期、三个同映射64 B请求3周期；越界和非法几何均拒绝。单token挑战测试前三次未进入测试即因运行时构造参数不完整失败，原日志保留，补齐与生产一致的chiplet/intra配置后通过。它们不是生产数值失败，也不计作通过的负对照。

CPU实际请求CLFLUSH/SFENCE，但当前有界源码检查未确认Sniper对缓存维护语义的完整建模；`cache_maintenance_timing_certified=false`。sim.out的ROI含codec、通信控制和等待，不能把整个ROI或“总时长减idle”直接当codec独立成本。寄存器操作、地址生成等控制开销未全部lower到NPU，不宣称完整目标时序。

## 尚需完成

新路径尚未接回完整连续两层，完整层759次矩阵仍使用先前通用计算代理；本轮没有偷换其旧通过证据。需要将其他实际M/N/K形状、向量/RMSNorm/softmax/SiLU/路由/布局/KV软件服务逐项迁入合法执行与资源成本；再做完整两层统一回归、显式DAG和缓冲复用/last-reader挑战。CPU缓存维护及软件服务分段成本仍需认证。

LPDDR5服务是研究代理，HB固定电气延迟未知；物理校准与HiBand/Sem-MoE净收益不在本轮通过范围。保留原GPU GEMM与softmax FP32差异，以及prefill输出4249元素、10路由槽位差异；无容差放宽、单输出补丁或新GPU参考。

来源：PROTOCOL.json、冻结生产源码、归档内FREEZE/BUILD_COMMANDS/RUN_EXIT/CPU_PASS/LOWERING/SRAM_ROWS/INDEPENDENT_AUDIT/CHALLENGES，以及本地两个独立审计回执。

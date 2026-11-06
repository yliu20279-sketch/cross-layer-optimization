# swe_qwen3 activation驻留、last-reader与NoC接收验证

收尾核验日期：2026-10-28（Asia/Shanghai）。状态：PASS_LIMITED_REAL_BF16_ACTIVATION_LAST_READER_NATIVE_NOC_RECEIVE；不是完整层、模型、物理性能或策略收益PASS。

## 固定合同与输入

原模型BF16、128 GiB host＋8 GiB HB研究overlay保持不变，原规范host8不改。固定既有R0002第0层moe_input，19个prefill token＋首个decode token，共20×2048 BF16；不新增模型/GPU/agent/SWE或留出访问。metadata沿用上一阶段759行中的前20行，保留phase内local_token、Top8 slot、expert ID及BF16 weight。softmax FP32七阶段差异继续FAILED_RETAINED，最大绝对差1.4901161193847656e-7，不因本轮收件正确而改判。

原始fixture及16份原生执行库/NoC桥接程序SHA由[独立审计](attempt2/INDEPENDENT_AUDIT.json)核对；具体绑定见[SOURCE_BINDING](attempt2/SOURCE_BINDING.json)。数值输入为既有真实fixture，activation在本轮原生HB store回调后建立驻留，不等于已执行上游完整层生产过程。

## 已完成的因果链

1. 将20份4096 B activation绑定到origin节点的实际HB区间，global_address=(rank<<29)+local_address；origin=phase内local_token%16。未驻留、跨节点直接HB读取均拒绝。
2. 复用同批CPU路由/metadata完成边界3739936 ns，在新上下文显式恢复并读回metadata；恢复完成3758063 ns。给15个远端origin发送紧凑metadata，远端接收可见后才允许该origin token分发。此次恢复不是重新运行完整CPU/H2D链路。
3. 每个activation记录8个独立slot读取者。源HB读完成并形成独立TX快照后才登记读取结束；8个读取者全部结束才退休源地址。正对照在原地址写入A5诊断字节，之后专家收件仍为原activation。
4. TX填充、显式SRAM drain服务完成后才允许NoC注入；TX保持到该消息全部尾包完成。目标RX暂存直到HB提交完成才能释放，专家入口读取必须晚于目标HB提交。
5. 接收端核对原32 B描述符、epoch、owner、slot、weight位型、body SHA和原fixture逐字节一致。160个inbox仍保留，expert_execution_ready=false；尚未绑定专家权重、执行MLP或消费inbox。

HB记录见[驻留](attempt2/ACTIVATION_RESIDENCY.json)、[last-reader和地址复用](attempt2/LAST_READERS_AND_REUSE.json)；跨域依赖见[通信账本](attempt2/COMMUNICATIONS.json)、[专家收件](attempt2/EXPERT_RECEIVES.json)。运行代码和协议分别由[FREEZE_v2](FREEZE_v2.json)封存。

## 验收结果

| 指标 | 修订后attempt2 |
|---|---:|
| 真实token / 专家分发 | 20 / 160 |
| 跨节点token消息 / 本地拷贝 | 146 / 14 |
| origin metadata消息 | 15 |
| NoC 128 B包 | 4850 |
| NoC线载荷（metadata＋远端token帧） | 620800 B |
| 全部分发token body（含本地） | 655360 B |
| HB读 / 写 | 1396032 / 904512 B |
| 原生32 B DRAM事务 | 71892 |
| 单节点SRAM峰值 | 105472 B |
| 16节点HB分配总量 | 822592 B |
| 门控负对照 | 597项通过 |

4850包=32个metadata包＋146×33个token包。本地14帧59136 B不记作NoC流量。每token帧含128 B头和4096 B body。fixture注入81920 B、诊断地址复用81920 B及metadata边界恢复60736 B均有显式HB服务，但不是自然工作负载净流量；不得据此宣称时延或带宽收益。

16-router活动子mesh的原生PopNet输入峰值8 flit、输出峰值1 flit，NI阻塞89327 cycles，逐周期容量检查开启。原生NPUSim/Ramulator事件、SRAM生命周期、packet ID集合和每消息全部尾包均由独立脚本重新核对，未假设包ID按消息连续或完成有序。每个源读取都晚于metadata就绪及activation生产完成，目标读取晚于对应尾包和HB提交。[本地因果复核](LOCAL_CAUSALITY_AUDIT.json)与远端源fixture审计分别记录，前者不声称在Windows重读远端原fixture。

## 修订与证据边界

attempt1保留：数据、尾包和生命周期检查通过，但漏计TX暂存到NoC/本地拷贝的SRAM读服务，不用于最终完整服务结论。修订不覆盖首版，见[TX_SERVICE_AMENDMENT](TX_SERVICE_AMENDMENT.json)；attempt2补显式drain及source_ready依赖后重新原生运行。

NoC原生桥接提供流控、容量和尾包时间证书；数值载荷在尾包证书后复制到接收暂存，桥接内部flit并非本负载BF16字节。因此这是“原生通信时序证书＋受门控数值载荷”的联合有限验证，不是逐flit数值传播或物理链路验证。依赖完整性不等于控制软件开销完整：metadata解析构建、header打包CPU成本、gateway物理传播未认证；SRAM为总容量/服务代理，未认证8 Bank逐Bank仲裁。

专家收件不等于专家可执行；专家权重驻留、后续真实算子、按源token/slot顺序commit、NoC返回与下游last-reader仍待推进。本轮不声称动态HiBand模式切换、Sem-MoE策略收益或全模型通过。当前两次新原生多上下文片段均计入历史：本线累计NPUSim片段6、Sniper ROI 3，物理NPU0；本轮新增GPU/agent/Sniper均0。该计数指实验片段，不指物理设备次数。

## 证据交付

原始两attempt证据先行封存424载荷，已本地核对外包及全部成员SHA；随后独立审计、报告一并重新封包，最终数量以[DELIVERY](DELIVERY.json)和[本地验包](LOCAL_DELIVERY_VERIFICATION.json)为准。旧失败和协议不覆盖。

下一步独立绑定专家权重后备/HB驻留与收件inbox消费者，验证专家计算及结果返回；SWE修复成功率继续与该功能路线分开。

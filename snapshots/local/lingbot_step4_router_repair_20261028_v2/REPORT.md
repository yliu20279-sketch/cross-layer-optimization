# LingBot步骤4：无GPU原精度功能适配与router修复

日期：2026-10-28。总体状态PARTIAL，不能认定完整步骤4数值准入通过。已完成本轮CPU功能适配、真实Golden核对、一个N0/CH0原生FP32 router行及router后处理修复。目标无GPU、原混合BF16/FP32、host128GiB/HB8GiB保持；没有FP16/量化替换或放宽逐位门槛，refiner排除。

## 1. 已确认的修复

v1两CFG共98869真实token行，Top8集合都与GPU一致，但98781行slot顺序不同。即使复用GPU scores，按expert对齐仍有7个BF16权重不同。v1代码、输出、审计全部保留在113原目录，当前包亦包含其审阅成员，不覆盖失败。

修复基于固定Torch2.6的源算法，而非按记录ID排序：unsorted TopK先按lane顺序gather严格大于阈值的元素，再补等于阈值的元素；E128和group E4均适用本次单迭代几何。不能把CPU torch.topk(sorted=False)当作CUDA槽位实现，也不能套用Qwen的sorted=True 32-wire排序网络。8项FP32 sum按对应Reduce.cuh的1/2/4 shuffle树实现，保持除法、乘2.5和最后BF16 cast的分界。BF16 RNE用独立整数位公式，与Torch在261120个有限编码及中点邻域值上逐位一致。

依据：[固定CUDA TopK调度](https://github.com/pytorch/pytorch/blob/v2.6.0/aten/src/ATen/native/cuda/TensorTopK.cpp)、[阈值gather](https://github.com/pytorch/pytorch/blob/v2.6.0/aten/src/ATen/native/cuda/TensorTopK.cu)、[Reduce配置/归约顺序](https://github.com/pytorch/pytorch/blob/v2.6.0/aten/src/ATen/native/cuda/Reduce.cuh)；实现见[router_contract.py](router_contract.py)。这里只声称固定版本/几何/已测数据，非任意CUDA TopK的API平局保证。

| 输入路径 | 正CFG 槽位差异行/权重差异元素 | 负CFG 槽位差异行/权重差异元素 |
|---|---:|---:|
| 原GPU FP32 scores→新Top8/归约/RNE | 0 / 0 | 0 / 0 |
| 原GPU logits→CPU sigmoid→新后处理 | 0 / 3 | 0 / 3 |
| 真实FFN输入→CPU GEMM/sigmoid→新后处理 | 0 / 45 | 0 / 48 |


原scores路径全部98869行ID和slot、790952个BF16权重逐位一致；不是把原ID/权重注入函数。独立NumPy用另一套实现从完整原scores重算group选择、ID、FP32分母与BF16 bits，309项检查通过，见[独立router审计](server_evidence/v2/INDEPENDENT_REPAIR_AUDIT.json)。保持新ID却使用CPU默认sum仍产生4个权重差异；过早转BF16再乘2.5，在两CFG分别产生107746/106105个差异，均未采纳。旧7个反例原/新ID、权重bits和分母保存在两份COUNTEREXAMPLES.json。

## 2. 尚未修复的router差异

同GPU logits输入后，CPU sigmoid产生的FP32 scores仍不逐位一致，最多绝对差1.1920928955078125e-7，并使6个最终BF16权重不同。因此RNE本身通过，不等于上游score可替换；这些BF16边界反例保留。自由CPU FP32 GEMM与sigmoid路径剩93个最终权重差异，槽位已修正为0差异。

源码实数sigmoid形式为FP32 1/(1+exp(-x))，见[固定UnarySpecialOpsKernel](https://github.com/pytorch/pytorch/blob/v2.6.0/aten/src/ATen/native/cuda/UnarySpecialOpsKernel.cu)。额外比较显式FP32 exp/add/div与标量libm expf（无fast-math、关闭FMA contraction），仍有7个最终权重不同，且FP32中间scores未通过，未接入候选。见[SIGMOID_PROBE.json](server_evidence/v2/SIGMOID_PROBE.json)及原位模式反例。不能靠提前BF16舍入、夹断、行号查表、强制写回原权重或放宽容差消除这些失败。

## 3. 实际功能覆盖

只用步骤3已见官方example_4的step0/layer0两CFG；正49883/负48986完整joint token（其中视频48360，其余为VLM条件序列，并非纯自然语言词数）。完整序列执行postnorm、残差到FFN输入和router；专家、共享专家、串联block各固定取前32视频行及最后32条件行。attention的64个查询保留全部对应49883/48986行K/V，不是缩短上下文后的推理。未执行整层所有输出、其他47层、40步目标闭环、VLM/VAE或最终TI2V全链。

[host_adapter.py](host_adapter.py)是明确的CPU host fallback候选：BF16矩阵输入/原权重逐tile解码为FP32临时工作区，FP32累加后在原边界回BF16；router、norm/time表仍FP32。特殊函数运行于host CPU，没有目标GPU。不是认证了BF16阵列，未套FP16吞吐。原层0相关权重所在分片重新全SHA核对，并记录tensor shape/dtype/raw SHA；原步骤3Golden亦按SHA核对。模型全量canonical后备及HB分区仍沿步骤1—2，未改原host8规范。

| v2对原GPU Golden的比较 | 正CFG差异元素 / 最大绝对差 | 负CFG差异元素 / 最大绝对差 |
|---|---:|---:|
| 完整序列 post-attention RMSNorm，原attention输出作为输入 | 651 / 0.03125 | 649 / 0.03125 |
| 完整序列 residual→norm2→mod，原postnorm边界输入 | 524 / 0.03125 | 571 / 0.03125 |
| 完整序列 post-FFN RMSNorm，原FFN输出作为输入 | 690 / 0.015625 | 739 / 0.0625 |
| 64查询行attention，保留全序列K/V | 14570 / 0.25 | 13524 / 0.25 |
| 64行共享专家 | 2166 / 0.5 | 2299 / 0.5 |
| 64行自由router MoE | 1656 / 0.5 | 2021 / 1 |
| 64行记录route replay诊断 | 1656 / 0.5 | 2021 / 1 |
| 64行原postnorm边界的残差commit | 0 / 0 | 0 / 0 |
| 64行完整上下文/自由router的串联block输出 | 10843 / 0.0625 | 12366 / 0.09375 |


两版各43项比较均为13项逐位一致、30项不一致；43中包括一项expert-order归约负诊断（本批恰好未产生反例），不能把它算作一次完整功能准入，亦不撤销其他工作线已有归约反例。记录route replay仅隔离下游，不算自由router通过。共享专家和MoE对同CPU源码也仍有数值差异，FP32拆分GEMM与BF16 CPU内核不能默认相同。RoPE同输入的所测head0/15以及slot restore同专家输出的CPU对照通过，均非完整GPU中间值认证。

独立全功能证据审计v1为71023项，v2为124项；重新计算保存的12个完整张量比较和全部review对照，保留上述失败。每版8项格式/ID/slot/位置/权重负对照通过；独立router另4项负对照通过。审计PASS仅表示证据一致，不改变总体PARTIAL。

## 4. 首个LingBot目标模拟片段

一个真实cond/step0/layer0/row0 router输入，原BF16 x[1,2048]、原FP32 W[128,2048]、FP32 logits，不将router输出改成BF16。复用只读NPUSim/Ramulator桥，N0/CH0活跃、32B事务、4MiB SRAM；FP32 vector按K升序显式乘加，数值在CPU求值，原生事件门控消费者，物理NPU0。

16651事件、33312个32B事务、524416个FP32 vector操作、SRAM峰值17408 B；独立依赖/容量/事务及4个runtime负对照通过。对独立顺序FP32参考逐位一致，但对原GPU128个FP32输出有121个不同，max_abs=2.47955322265625e-5，保持PARTIAL。见[片段状态](server_evidence/v1/native_router/STATUS.json)、[v1独立审计](server_evidence/v1/INDEPENDENT_AUDIT.json)。这证明事件/软件路径有限可运行，未证明原GPU GEMM归约顺序可由顺序K替代。

原始mixed输入/权重1052672 B，临时FP32预置1056768 B，仅BF16输入需解码；FP32输出导出512 B。片段代理周期250447不含host codec、PCIe/gateway或完整router sigmoid/Top8，不能作完整router/层延迟。未认证SRAM Bank仲裁、CP16/EP16通信、动态分页、HB全活跃集或HiBand/Sem-MoE收益。本线累计NPUSim片段1、物理NPU0、新GPU运行0；v2 CPU脚本里的simulator_runs=0仅指该次CPU脚本，本总体记录包含此前一次片段。

## 5. 留存、失败与交付

两次功能运行均退出0，v1约76.30s、v2约73.51s，RSS峰值约6.26GiB（不是目标时延/容量峰值认证）。单worker、8 CPU线程、24GiB RSS/2400s上限，GPU不可见。初次上传曾被自动审批服务额度阻断，用户继续后按原审批流程重试成功；无绕过。router候选首次因Torch2.6 stable argsort需要dim关键字失败，原代码/冻结/log保留，修正API形式不改数值算法。旧v1失败、标量sigmoid未通过方案均保留。

远端完整两目录输出封包时320文件、3134498886 B，完整成员SHA在[REMOTE_FILE_MANIFEST.json](server_evidence/v2/REMOTE_FILE_MANIFEST.json)；完整CPU张量及原步骤3Golden仍留113。本地明确为review子集：297成员、400987862 B，外层68349263 B、SHA256=a992577bb135861c819101230dd84564686224d06f0a2304a85c92e6c83dfcab，外层和全部回收成员通过SHA，见[LOCAL_VERIFICATION.json](LOCAL_VERIFICATION.json)。本地包含两版metadata、原生trace/小型载荷、全部review pairs、router修复全量ID/权重/归约数据及失败；没有宣称3.13GB完整CPU输出已回传。

下一项应先确定可独立验证的FP32 GEMM归约和sigmoid host软件合同，再处理BF16专家矩阵及attention的具体舍入；当前不晋级完整层/模型或性能矩阵。不能把同score路由通过推广为sigmoid/GEMM/整层通过。

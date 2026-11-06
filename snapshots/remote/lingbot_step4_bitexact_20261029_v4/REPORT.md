# LingBot步骤4：rsqrt/exp、GEMM与串联层输出修复

日期：2026-10-30；目录名沿用29日。当前总体仍为PARTIAL，全部查询行的单层验收正在后台进行，不能写步骤4已完成。此前各版失败、旧原生片段的GPU差异均保留。

已通过范围：同一已见example_4、layer0/step0、条件/无条件两分支，各64个预定查询行，全部49883/48986真实K/V。全部计算运行于CPU，保持原BF16/FP32、host128GiB/HB8GiB；无FP16替换、无FP64模型计算、目标GPU为0，无refiner。并非独立留出或TI2V端到端认证。

| 合同 | 已核实结果 | 原始回执 |
|---|---|---|
| rsqrt与四个完整postnorm | 197738个FP32因子、404967424个BF16元素逐位一致 | RSQ_RESULT.json |
| 自主router全序列 | 12655232个FP32 logits及scores、98869行Top8槽位、790952个BF16权重逐位一致 | FREE_ROUTER_RESULT.json |
| 完整K/V投影 | 四个投影共404967424个BF16元素逐位一致；来自自主CPU输入 | FULL_KV_RESULT.json |
| attention前半段 | 完整norm1/modulation与选定64行Q/K/V及QK norm逐位一致 | ATTENTION_FRONT_RESULT.json |
| 共享/记录路由MoE | 两分支各64×2048输出逐位一致；该项单独仍为记录路由诊断 | TC_SHARED_RESULT.json、TC_MOE_RESULT.json |
| 串联attention及层输出 | 两分支×attention/FFN输入/FFN输出/postnorm/block输出共10项、1310720个BF16元素逐位一致，无中间Golden注入 | CONNECTED_BLOCK_V2_RESULT.json |
| 独立审计 | 67项检查、12项负对照；131072元素独立BF16 RNE检查通过 | INDEPENDENT_AUDIT.json、GUARD_AUDIT.json |

修复原因与实现：rsqrt/exp须复现原GPU特殊函数近似，数学上正确RNE不自动等于原实现。使用与模型输入无关的完整指令域表在CPU查原FP32位值；EX2遍历全部2^32个输入位模式，RSQ遍历两种指数奇偶下全部2^23尾数，不是按token、专家或Golden修补。数学表SHA见SFU_SHA256SUMS.txt。

router原核为FP32 FFMA、5路交错split-K：分区p处理K块8p+40i，块内FMA，最后按0至4作FP32加法。此前顺序、条带及连续split-K候选未通过且保留。专家及Q/K/V使用H100 BF16 FDA16/neab2的整数对齐软件实现，CPU SIMD版本经100000组独立原语挑战及真实524288元素分块逐位核对。

attention按实际PyTorch 2.6 native_flash的128×64非因果分块，逆序访问K/V。其源码UNFUSE_FMA要求exp2前乘减分开舍入，最终归一化采用FP32除法。原FMA候选及近似倒数候选失败保留。RoPE采用复数乘法对应FMA边界；未重算或降低原complex64输入精度。输出投影有原BF16 bias，须先FP32加bias再回BF16；遗漏bias的串联失败、先回BF16再加bias的32940/34251差异均保留。

资源边界：EX2表16GiB、RSQ表64MiB；另保留32MiB未采用的RCP候选，保守总预算余11847728052B（约11.03GiB）。这是静态host容量准入，不是实际host/HB分页、缓存流量或目标时序验收。未来所有策略分支必须使用相同数学表并计入访问成本；不能以CPU软件耗时推目标NPU性能。

本v4新增7次有界外部GPU原语/子模块参考任务，完整模型调用0；CPU目标运行无GPU。新目标原生0、物理NPU0；LingBot历史原生累计1仍仅旧router片段，不继承为GPU逐位PASS。没有HiBand/Sem-MoE/Bank/NoC收益结论。

全部查询行验收已单独启动：98869行，两分支均保留完整K/V，16 CPU线程、nice10、最长12小时，逐64行保存检查点，首个数值差异立即停止并保留输出；不运行48层/40步矩阵。进度见full_query_acceptance/STATUS.json、all_queries.log。完成后finish_all_queries.py自动独立重载全部输出、路由、覆盖及成员SHA；只有INDEPENDENT_AUDIT.json通过才是完整单层有限合同通过。当前64行通过不能替代该结果。远端任务不依赖本机开机/连接。

权限验收为Unix other读/父目录遍历位检查，不是另账号登录实测；见PERMISSION_AUDIT.json。大型指令表、完整K/V及完整Golden输出留113；本地交付为review子集，不能把review成员数写成全量回传。

方法来源：[硬件舍入软件模型，固定提交3f7cdf7](https://github.com/NaciCankaya/hardware_rounding_error_predictor/tree/3f7cdf7010a9fe691bb5832755f668556edcc217)，保留Apache2 LICENSE，未继承其其他模型/设备PASS；[PyTorch v2.6 softmax原源码](https://github.com/pytorch/pytorch/blob/v2.6.0/aten/src/ATen/native/transformers/cuda/flash_attn/softmax.h)、[attention原源码](https://github.com/pytorch/pytorch/blob/v2.6.0/aten/src/ATen/native/transformers/cuda/flash_attn/flash_fwd_kernel.h)。模型/输入绑定沿用步骤3FIXTURE_MANIFEST和WEIGHT_REFERENCES；本轮未重新哈希全部70GB原权重。

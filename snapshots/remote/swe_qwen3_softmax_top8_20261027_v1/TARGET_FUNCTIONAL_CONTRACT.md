# Softmax/Top8：目标功能合同与平局边界

精度不变：源BF16 logits→FP32 softmax→FP32 Top8/renorm→int64 expert ID＋BF16最终weight。目标host128GiB＋HB8GiB overlay保持，原host8规范不改。

## 目标放置

本轮显式采用x86 host软件回退，程序在目标CPU Sniper代理中执行；不向NPU添加exp、TopK或整型控制指令，也不把host实现当NPUSim vector执行。NPU router投影的已有BF16/FP32软件路径仍是另一子合同。

可选入口route_adapter.SourceCudaRoute128.from_logits只收inference CPU BF16 [...,128]，返回FP32 probabilities、int64 selected和BF16 weights。旧bf16_adapter.py及旧51合成CPU合同不改。当前有限域为非空E128/k8、有限BF16 logits；NaN/Inf logits、负概率及负零概率显式拒绝，未声称复现源非有限值行为。

## 平局规则的来源与范围

固定PyTorch2.6.0+cu124、git2236df1770800ffea5697b11b0bb0d910b2e59e1。官方TensorTopK.cpp/.cu与当前安装的SortUtils.cuh、SortingCommon.cuh、Sort.h支持本次算法绑定；头文件SHA见attempt1/INDEPENDENT_AUDIT.json。

对当前E128，源CUDA选择分支可按单block128线程的逻辑顺序展开：先取严格超过第8值的项，再补足遇到的边界相等项；随后按源32-slot不稳定网络处理选中的8项及padding。实现使用等价阈值计算，不移植GPU radix指令；有限正概率域内比较次序一致。专家ID不是最终稳定排序的secondary key，网络交换会改变相等项的slot顺序。这里复现特定backend分支，不能推广为torch.topk所有版本、维度或非有限域的统一承诺。

主实现只读logits或probability，不读取记录ID。gold_IDs.bin是已采集真实dispatch的比较文件，名称不是SWE gold patch；它只在验证器中作为期望输出。编译的route_kernel无文件输入，Sniper程序参数也只有logits路径和输出路径。未访问SWE gold或隐藏测试。

## 分开判定

1. 以捕获GPU FP32 probability为真实输入：Top8 ID/slot、BF16权重必须逐位一致。当前759行全部通过，包括80行边界平局。
2. 从捕获BF16 logits自行计算softmax：最终ID/slot/权重当前759行全相等，但FP32概率不逐位相等。原严格中间值检查保留失败；不能以BF16结果相同提升为完整子链GPU数值PASS。
3. 合成5例验证重复性、合法集合、underflow等边界；未新跑GPU合成oracle，因此不把它们称独立GPU认证。
另外两个固定CPU反例证明，FP32 exp舍入及下溢可使不同BF16 logits变为相等概率，此时Top8(logits)与Top8(softmax(logits))的专家集合不同。不能为了省略softmax而把选择前移到logits；PROBABILITY_TIE_PROBES.json只提供CPU语义反例，不冒称新GPU实测。
4. Sniper核查实际CPU执行的输出位型，不等于NPU原语、CPU-NPU传输或完整系统时序认证。759行合并为冷ROI批次，不是自然session调度，也不据此推算在线逐请求耗时。

## 数据与下游依赖

本实现的批量数组载荷：BF16 logits194304 B、FP32概率388608 B、int64 IDs48576 B、BF16 weights12144 B，合计643632 B；这是显式数组payload，不是包含stack/allocator/cache的实测host峰值。纳入现有1GiB IO预算，不扩大128GiB host；没有HB新增驻留或SRAM分配认证。

若前级BF16 logits在NPU/HB，每token逻辑D2H256 B；host输出Top8 metadata为64B IDs＋16B weights，即逻辑H2D80 B。若沿上一阶段“FP32 router输出D2H、host回写BF16”的路径，CPU已有logits，不再重复计算另一份D2H256 B。两种入口是替代合同，不能叠加，也不能漏掉上一阶段已有512B FP32导出。

80B只是逻辑metadata，32B事务对齐、256B包、DMA描述符、NoC传送及完成回调尚未在本轮接入，不宣称这些成本为零。下游dispatch须在CPU route完成及metadata传输完成后release，且保留已验证的专家升序BF16合并；固定真实ID不能提前提供给未来层预测/在线调度。

来源：[TensorTopK.cpp](https://github.com/pytorch/pytorch/blob/v2.6.0/aten/src/ATen/native/cuda/TensorTopK.cpp)、[TensorTopK.cu](https://github.com/pytorch/pytorch/blob/v2.6.0/aten/src/ATen/native/cuda/TensorTopK.cu)、[Sort.cu](https://github.com/pytorch/pytorch/blob/v2.6.0/aten/src/ATen/native/cuda/Sort.cu)、[SortUtils.cuh](https://github.com/pytorch/pytorch/blob/v2.6.0/aten/src/ATen/native/cuda/SortUtils.cuh)；本轮route_kernel.cpp、PROTOCOL.json与原NUMERIC_CONTRACT。

# Legosim统一入口/BF16检查与swe_qwen3接入准备

结论：已经定位并检查统一入口，完成本地接入构建适配器与重排计划；**尚未接入完整工具链，也未完成统一入口实验**。源码上传与远端编译被自动审批拒绝，未绕过。原BF16/host128 GiB/HB8 GiB保持不变。

## 已确认的入口与版本差异

交付归档D:/electronic_science/LLM芯片及系统优化/跨层优化/system_chip/261018/LEGOSIM_MICRO.zip包含InterChiplet、NPUSim、Ramulator2-Chiplet及模板。本目录source选择提取904份源码/配置，逐文件SHA见SOURCE_MANIFEST.json；并非完整第三方依赖可执行交付。

统一入口是interchiplet/bin/interchiplet：读取phase1/phase2 YAML，启动计算/存储进程，收集通信trace，由PopNet生成delayInfo用于后续轮次。模板真实命令为interchiplet <yaml> -w <width> -f 4 -t <rounds>；-t是轮次上限，不是wall timeout。源码与模板见source/interchiplet/srcs/interchiplet.cpp、source/NPUSim/templates/npu_workload/Makefile及cpp_chiplet.yml。

113已核对的旧根/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO不含NPUSim，其InterChiplet启动报缺libboost_system.so.1.65.1。系统已有Boost1.71库与头文件。此前实际运行使用的NPUSim源副本位于/mnt/sda1/h3240101068/olmoearth_v3_6_integration_20261025_v1/source/NPUSim，不能据此认定旧统一入口已集成它。有界搜索未发现另一可直接复用的完整入口；不是整台服务器不存在证明。

现成qwen3_v1/qwen3.yml为Qwen3-8B、CPU+GPU+NPU+128 MiB共享DRAM，不能用于本MoE/no-target-GPU/HB8配置；模板NPU参数与V3.6也不同。不能只替换benchmark名或权重路径。

## BF16支持结论

交付npusim_tensor_codec.h有kBf16=3、两字节payload与RNE编码/解码；runtime的2-byte默认仍是FP16，必须显式声明各dtype。FP32 norm/router/softmax不能被全局BF16设置覆盖。npusim模板说明时序事件不做功能计算，功能实现须与事件对应。

因此codec/线协议支持存在；完整Qwen3混合精度、CPU/NPU实际服务时序、真实BF16阵列吞吐没有由统一入口认证。不能套FP16 MAC性能。旧报告../swe_qwen3_bf16_executor_audit_20261026_v1/REPORT.md的有限codec与通用op缺项结论仍有效；本轮静态源核查不是重新执行该全位型探针。

## 本轮实际交付

build_entry/CMakeLists.txt：在隔离目录构建真实InterChiplet/C协议库，使用已有Boost，不要求入口自身开启CUDA，不修改交付源或共享安装。尚未编译通过认证。

launch_legosim.py：提供inspect/build-entry/launch入口，launch最终调用真实InterChiplet，不调用旧Python事件桥冒充集成。INTEGRATION_CONTRACT.json明确BF16/host128/HB8、目标GPU0及16NPU，所有未验条件为false，当前必须拒绝启动；不是已跑通或已实现完整payload driver的证据。缺失driver/YAML/拓扑必须实际补齐并验收，不能手改布尔值代替回执。

REPLAN.md：给出从统一入口修复、BF16真实payload/存储往返、V3.6容量拓扑、功能原语移植、Sniper host计费，到完整单层/两层和phase反馈的顺序及出口标准。此前累计原生19等局部运行不增加，本轮统一运行0、目标GPU0、物理NPU0，无SWE/agent/新留出访问。

## 当前阻断

自动审批拒绝将本地交付源码上传113并创建隔离构建，理由是“用户授权完整工具链接入，但未明确授权这份源码向该具体目的地外传”。拒绝发生在执行前，没有上传此源码包、没有远端构建。本地其余准备已完成，待用户批准具体源码包及113目的地后再实际执行。此前报告/审计/状态上传授权不等同此源码上传授权，故未重试。

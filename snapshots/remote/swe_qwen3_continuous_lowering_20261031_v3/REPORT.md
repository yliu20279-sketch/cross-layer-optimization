# swe_qwen3 完整两层 CPU / FP32 / SRAM 接入验收

2026-11-01 核验。状态：PASS_LIMITED；步骤1—7仍为PARTIAL。

## 已完成范围

隔离流式v3于2026-10-31完成真实统一工具链两轮，RUN_EXIT.returncode=0，耗时42865.264秒。每轮包括19-token prefill与1-token cached decode连续两层，759矩阵/32形状、374向量调用、4320 Sniper CPU软件调用。759个即时FP32门控共1626944元素逐位通过，56阶段文件及12项层输出/KV严格检查通过，CPU最终双回传完成。

每轮220495项I/O SRAM门控、48393049 I/O SRAM周期；矩阵计算事件288457056，矩阵Bank周期2201039424。水平PopNet98079条、域服务536131条、总传输634210条；第二轮实际加载反馈，全部70项控制器子进程退出状态为0。两轮完成不等于反馈收敛，报告的周期变化10.115%保留；仿真周期不是物理性能。

## 独立审计与归档

[本地独立复核](LOCAL_SAFE_AUDIT.json)重验613成员的大小与SHA，以及两轮数值、依赖、时钟和FP32门控。安全包128777679字节，SHA256为a9f9c916059825f383ddadcdf72847b32769800f0c090588e0e25fbfcc98728e。

原始证据：[数值审计](safe_review/swe_qwen3_continuous_lowering_20261031_v3/RAW_ORACLE_AUDIT.json)、[运行退出](safe_review/swe_qwen3_continuous_lowering_20261031_v3/RUN_EXIT.json)、[完整审计](safe_review/swe_qwen3_continuous_lowering_20261031_v3/INDEPENDENT_AUDIT.json)。外部二进制和完整16GiB数学表未在本地重新全量哈希，其113侧审计与来源记录保留。

## 尚未通过

本版每轮768项布局来源缺口未消除；缓存维护完成时序、部分控制与动态释放未认证。保留所有不可变缓冲的last-reader核对不等于动态回收证明。单共享端口/32字节条带属于显式Bank研究点。不能据本版声称完整目标时序或策略收益。

原BF16、host128 GiB/HB8 GiB不变，源规范host8 GiB未改。保留对原GPU的4249个prefill输出元素及10个路由槽位差异和softmax FP32差异；新GPU/SWE/物理NPU运行均为0。16GiB指数表与128KiB SiLU表是模型无关软件兼容数据，计入host容量及访问，不是新增模型权重。

v1标量构建修订停止、v2整块接收暂存容量修订停止，原记录保留；两者不能作为数值失败或完整通过。v3流式接收后才完成上述有限验收。

后续隔离修订见[布局与缓存工作记录](../swe_qwen3_alias_cache_20261101_v4/REPORT.md)，不得以CPU控制回归替代原生重跑。

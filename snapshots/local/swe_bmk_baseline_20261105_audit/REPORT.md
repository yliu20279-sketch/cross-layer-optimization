# 2026-11-05 基线收尾核查

状态 PARTIAL。113 四个诊断进程 4042961—4042964 已发送 TERM，后续 ps 确认均退出。

v7 首个监控断言定位到第二轮 cpu.log 第36544339行。token 36169087、地址93824992902784、prefix36169086，编号递增且未重复。原始行是
MAINT_WRITE_ACK 36169087 93824992902784 4624275465616480 4624275[RESPONSE][INTERCMD] RESULT 1 .././buffer0_12_0_4
下一编号36169088正常。监控正则将被其他日志插入的完成时间前缀4624275识别为完整时间，触发end>=start断言。已确认日志交错导致解析失败，尚不能据此证明真实回调时间倒退。watch_cache_live.py捕获异常后向运行组发送TERM，RUN_EXIT returncode=-15与此一致。应隔离修复结构化日志输出及严格记录边界，再做有界回归，当前不晋级完整缓存链。

P0-1b v11 在113重跑 audit_model_v2.py，Qwen3 136二进制成员与v10逐位一致、路由槽及权重一致、64批双请求KV；Qwen1.5为40成员、16批。两者返回PASS_LIMITED_DUAL_MODEL_KV_READ_CONCURRENCY。该审计检查每批issue/issue/complete/complete及同批编号，尚未独立证明物理服务时间交叠。权限相关负例原回执alias/fixed_object/stale_generation/over_budget均拒绝，本轮未重跑负例。INPUTS等索引自身SHA已保存，未重哈希索引所有载荷。正式性能仍false。

来源远端 /mnt/sda1/h3240101068/swe_qwen3_continuous_portable_20261101_v7/{watch_cache_live.py,LIVE_CACHE_FAILURE.txt,RUN_EXIT.json,run1/proc_r2_p1_t0/cpu.log} 和 /mnt/sda1/h3240101068/ca_p0_1b_native_20261103_v11/{audit_model_v2.py,evidence/PHYSICAL_PERMUTATION_NEGATIVES.json}。
本地独立重跑输出见 V11_RECHECK.txt。D盘指定归档尚未写入。

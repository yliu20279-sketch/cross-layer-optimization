# 异常分片根因与修复（2026-10-26）

确认原因：旧本机relay.py在已经发送200/206响应头并开始流式传输后，捕获异常又调用send_error(502)，把HTTP响应头和HTML错误页写入同一权重响应体。curl断点随后按已落盘字节数续传，未纠正局部污染。因此大小达到预期仍可SHA256不匹配。HTTP错误页记录的底层异常为[Errno 2] No such file or directory；其更底层触发原因未独立重现，不将它当作113模型目录缺失的证据。

证据：CORRUPTION_SCAN.json在文本编码器第1/第2及transformer第1分片分别发现4/1/4处HTTP/1.0 502，含BaseHTTP/0.6 Python/3.13.5及02:53—03:21 UTC时间，属于旧本机转发阶段。PREFIX_DIAGNOSIS.json、RANGE_BOUNDARY_DIAGNOSIS.json及48项分布抽样未发现版本差异；抽样本身不替代全文件哈希。官方ModelScope固定修订与冻结HF清单的权重SHA一致。

修复方法：停止状态下保留损坏原件到远端corruption_evidence，复制出待修复文件；仅从官方ModelScope固定修订读取9处污染附近的8192B区间，随后全文件SHA256符合冻结清单才转为完成文件。每份结果见REPAIR_RESULTS.json；不删除原件，不覆盖已有通过校验文件。

后续v3下载使用113独立直连ModelScope，不使用本机relay；对每文件完成立即验证，损坏分片保留并有限重试、独立记录FAILED_FILE，避免v2因按提交顺序等待future导致异常延后显示。单进程文件锁防重复写入，已有已验证文件重验后保留。仍排除refiner；完成后全141文件再验哈希、权重索引闭合、755/644及ACL，生成最终机器回执。源码/权重下载认证不等于推理、依赖或收益认证。

修复验收结果：3/3全文件SHA256一致，9个区间合计73728B；原件保存在corruption_evidence。v3 PID2879963已启动，13:31:19 UTC新第4分片已25178112B，errors=[]，最终下载验收尚未完成。见REPAIR_RESULTS.json与V3_PROGRESS_CHECK.txt。

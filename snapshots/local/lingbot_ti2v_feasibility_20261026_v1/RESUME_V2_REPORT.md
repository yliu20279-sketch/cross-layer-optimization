# 2026-10-26 服务器独立续传修订
用户明确授权恢复下载并保留断点。旧11:37失败和本机转发版脚本/日志保留。V2使用113直连官方ModelScope固定修订057a08df568ddbd91efaf49944e8604ba3172a3a，不依赖本机持续开机。46份模型文件大小匹配，LFS文件SHA256与原HF冻结清单一致；README/.gitattributes不匹配，保留原已完成版本。最终一律按原DOWNLOAD_MANIFEST.json大小、LFS SHA256或Git blob逐项验收，不以镜像同名替代同一性证明。
源码固定提交归档已一次性上传，93份文件逐Git blob核验通过。旧3份大文件断点保留并已观察增长，13:58回执见RESUME_V2_RECEIPT.txt。123个最终命名文件已存在（包含源码），大权重仍在下载；不能将文件数量当完成字节比例。
后台PID2585253，脚本download_base_v2_server.py，日志download_v2_server.log；60次有限递增重试、curl Range续传。完成后复核141文件69694390066B、模型索引引用、refiner不存在、目录0755/文件0644，生成FINAL_VERIFICATION.json。当前未完成，不宣称最终哈希或权限验收。目录ACL本轮抽查仅基本条目且other::r-x，无跨账号切换实测。未启动推理、依赖安装、训练或模拟器。

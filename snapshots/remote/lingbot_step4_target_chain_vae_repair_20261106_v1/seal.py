from pathlib import Path
import hashlib,json,tarfile
R=Path(__file__).resolve().parent;S=R.parent/'lingbot_cpu_vae_repair_20261105_v1'
a=json.loads((R/'ACCEPTANCE_RECEIPT.json').read_text());assert a['state']=='PASS_LIMITED_REPAIRED_CPU_VAE_TARGET_BOUNDARY_CHAIN'
report="""# CPU VAE修复及有界目标链验收

状态：PASS_LIMITED_REPAIRED_CPU_VAE_TARGET_BOUNDARY_CHAIN。仅对冻结 example_4 首帧和有界 CFG/scheduler/next-latent tile 验收，不晋级完整系统成本或收益。

首个分歧是 decoder.conv_in：CPU默认卷积的累加顺序与冻结GPU不同。修复为输入/权重驱动的顺序FP32 FMA及独立bias加法。继续定位并实现了布局对应的RMS归约、模型无关EX2指令兼容的SiLU，以及实际SM80 FastF32三路TF32/FDA、阶段临时累加、在线softmax与PV合并。串联检查还发现Conv2d输出布局改变后续归约分支，已恢复GPU对应NCHW布局。没有使用GPU中间张量、首帧或差值修正CPU输出。

127次同输入算子/注意力块检查合计1978129920个输出元素零差异；完整CPU串联第一次仍失败并保留FULL_CPU_FRAME_AUDIT.json，第二次修复布局后通过。独立TF32原语128组、QK中间值观测与GPU内核输出同一性证据留在同级repair目录。所有验收保持FP32逐位标准。

本目录两轮真实NPUSim HB/SRAM、外部Ramulator 32B服务、InterChiplet字节回传和PopNet回放完成；8子进程退出0。两轮CPU VAE首帧1198080个FP32值均对冻结GPU零差异，量化差异0，双轮输出逐位一致。CFG/scheduler/next latent各2048元素通过；具体反馈条数和完成顺序见ACCEPTANCE_RECEIPT.json及case*/N00/EVENTS.json。第二轮加载第一轮反馈，不声称收敛。

参考注入：冻结双CFG预测及scheduler输入tile；另在DiT到VAE边界注入冻结40步最终latent首时间片，未执行剩余39步，不代表从当前scheduler更新连续生成最终帧。其余120帧未覆盖。

未覆盖成本：CPU原生服务耗时未进入目标时钟，本链PCIe DMA、缓存写回时序、完整逐MAC/ISA和兼容指令表访存成本未闭合。16GiB完整EX2指令域表是模型无关软件兼容依赖，不能视作免费算子或纯NPU执行。目标GPU调用0；诊断GPU仅作外部参考。未运行正式PK或CA消融，promotion=false。

证据仅保存113。一键新目录复跑入口：rerun_isolated.py，参数必须是不存在的同级新隔离目录。
"""
(R/'REPORT.md').write_text(report)
for root in [S,R]:
 rows=[]
 for p in sorted(root.rglob('*')):
  if not p.is_file() or '__pycache__' in p.parts or p.name in ['MANIFEST.json','DELIVERY.json','evidence.tar']:continue
  rows.append(dict(path=str(p.relative_to(root)),bytes=p.stat().st_size,sha256=hashlib.file_digest(p.open('rb'),'sha256').hexdigest()))
 (root/'MANIFEST.json').write_text(json.dumps(dict(payloads=rows),indent=2))
with tarfile.open(R/'evidence.tar','w') as tar:
 for p in sorted(R.rglob('*')):
  if p.is_file() and p.name not in ['evidence.tar','DELIVERY.json'] and '__pycache__' not in p.parts:tar.add(p,arcname=str(p.relative_to(R)),recursive=False)
p=R/'evidence.tar';d=dict(state=a['state'],archive_bytes=p.stat().st_size,archive_sha256=hashlib.file_digest(p.open('rb'),'sha256').hexdigest(),evidence_location='113 only',repair_manifest=str(S/'MANIFEST.json'));(R/'DELIVERY.json').write_text(json.dumps(d,indent=2));print(json.dumps(d))

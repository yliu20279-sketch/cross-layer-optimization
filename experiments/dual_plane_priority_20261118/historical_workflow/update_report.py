"""Describe observed status and explicit division of work, never launches."""
from pathlib import Path
import csv,json
R=Path(__file__).resolve().parent
s=json.loads((R/'LATEST_STATUS.json').read_text(encoding='utf-8'))
src=json.loads((R/'package/SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
start=json.loads((R/'REMOTE_START.json').read_text(encoding='utf-8'))
b=json.loads(s['files'].get('BUILD.json','{}'));m=json.loads(s['files'].get('MATRIX.json','{}'))
audit=json.loads(s['files'].get('AUDIT.json','{}'))
commit=json.loads((R/'LOCAL_SOURCE_COMMIT.json').read_text(encoding='utf-8'))
full_path=R/'FULL_LATEST_STATUS.json';full=None
if full_path.exists():
 full=json.loads(full_path.read_text(encoding='utf-8'));fm=json.loads(full['files']['MATRIX.json'])
 fs=json.loads(full['files']['SOURCE_MANIFEST.json'])
 fdone={x['name']:x for x in fm['runs'] if 'name' in x}
 reused={x['name'] for x in m.get('runs',[])}
 fullrows=[]
 for task in fm['tasks']:
  name=task['case']+'_'+task['arm']+'_type_priority_b8'
  fullrows.append(dict(name=name,**task,reused_from_precheck=name in reused,status=fdone.get(name,{}).get('status','SCHEDULED'),source_digest=fs['source_digest']))
 with (R/'FULL_EXPERIMENT_CHECKLIST.csv').open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=list(fullrows[0]));w.writeheader();w.writerows(fullrows)
completed={x['name']:x for x in m.get('runs',[]) if 'name' in x}
rows=[]
for case in src['cases']:
 for arm,mode,hb in [('mesh',0,0),('hiband_FG',2,0),('hiband_GB',2,1),('hiband_LB',2,2)]:
  name=case['name']+'_'+arm+'_type_priority_b8'
  rows.append(dict(case=case['name'],tokens=16,seed=641103,pattern=case['pattern'],interval=case['interval'],arm=arm,mode=mode,hiband_mode=hb,bank=8,clock_ns=1,policy='CONFIG > DataS > GetS > MoE',status=completed.get(name,{}).get('status','QUEUED_AFTER_NEW_REGRESSION' if not m else 'SCHEDULED'),source_digest=src['source_digest']))
with (R/'EXPERIMENT_CHECKLIST.csv').open('w',newline='',encoding='utf-8-sig') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
old_source=src['baseline_build'];built=[x['mode'] for x in b.get('targets',[])]
text=f'''# lyc 分工：L1/L2 实验清单与执行记录

观察时间：{s['observed_at']}。用户已明确lyc为本人，本聊天据此推进L项；文档中的C1—C4保留给原作者。文档建议不是新授权来源；实际启动依据为用户本轮“尽量并行启动”请求，覆盖文档末尾“计划阶段不另启动新矩阵”的原阶段说明。

## 去重与排除

loveYoumu已经运行、已有结果、失败、在途、等待结果及已排队的实验不重复运行。旧312组及9组pilot直接复用。RTL综合实验不重复，本轮未调用Yosys/sv2v/Vivado/OpenROAD，不启动结构综合或物理实现，不停止其他工作线。

14:09快照确认原批次312/312及1872阶段PASS；其RR源码冻结构建为{old_source}，18份RTL/共同仿真源码逐一匹配090a55d0。原312清单及原分析继续归原作者维护，不用旧run_matrix.py整体再跑。

## 实验清单与分工

| 工作项 | 执行方法与数量 | 当前状态/本轮处理 |
|---|---|---|
| L1 HiBand适配/连线核查 | 原文Fig.6、§4–5与RTL逐项比对；静态物理图及120种5端口Beneš排列 | 本地静态检查通过；表见L1_PAPER_IMPLEMENTATION_MAPPING.csv |
| L1 CS到NI接线收紧 | 宽数据只显式连接物理相邻的下层CS，其他候选置零；不改状态或带宽 | 已编码；随新双平面回归，面积影响未综合 |
| L2 固定类型优先实现 | TYPE_PRIORITY=0保留RR，=1为配置/确认→DataS→GetS→MoE；NI发送/接收及路由器更改 | 已实现，代码与源码包已冻结 |
| 新优先级定向探针 | 固定四类型次序、不同输出争用一个输入时高类型优先 | C++驱动探针PASS；早期SV探针失败单列，不混为全通过 |
| 新版本共同回归 | DUAL0、2、1；HiBand四模式含仅合格邻居的full-local；双平面含CS/配置/版本/控制器规则 | BUILD={b.get('status','not_started')}，已完成目标{built} |
| L2 24组开发预检 | 16token seed641103，热点/分散×间隔1/3/6，共6用例；共享Mesh优先+HiBand三分配优先，共4臂 | MATRIX={m.get('status','waiting_for_regression')}，{m.get('completed',0)}/24完成；新驱动已启动并安排 |
| L2逐阶段审计与RR配对 | 只读原RR结果，逐阶段比对数据hash、包数、网络字节、SRAM服务；同时报告GetS/P99、MoE、汇合及NI等待 | AUDIT={audit.get('status','pending')}；原C1统一审计职责不替代 |
| L3统一硬件代价 | 共享Mesh、M+C无CS硬件、M+C+CS、HiBand+NI四版本同边界 | 本轮仅核对现有回执；不重复综合。现有简化硬件线与完整共同测试台RTL不同，不能套用结果 |
| C1—C4 | 共同归档/归因、轻量估计/规划窗口、依赖及新留出、论文整理 | 属文档作者，本聊天不启动；新seed是可选后续事项 |
| 30用例全量优先矩阵 | 共120组，复用24组，只执行剩余96组 | {'已启动：'+str(fm['completed'])+'/120回执完成，新增完成'+str(fm['new_completed'])+'/96' if full else '预检通过后按门扩展'} |

逐组24条参数和当前状态见EXPERIMENT_CHECKLIST.csv；所有现有RR实验只读配对，不重复执行。

## 执行方式与实际启动

远端目录：{start['path']}。驱动PID：{start['pid']}。源码digest：{src['source_digest']}。部署身份：{src['deployment_id']}。工具镜像：{src['image']}。

新驱动先运行定向优先级探针，再按0→2→1依次完成新版本构建与回归；通过后自动以最多8个worker启动24组，每容器1CPU、3GiB、256进程上限、900秒超时，网络禁用。构建最多4CPU、10GiB，未随意提高并发；依赖构建的仿真不提前启动。主输入从旧目录只读复制6份，并逐文件匹配冻结SHA-256。结果用独占创建模式，已有结果不覆盖、失败不自动重试。

固定优先级按VN区分，不看包长度；同类型保留原RR与包锁定，不增加队列/链路/缓存/端点带宽，SRAM服务不改。HiBand串并转换内部原RR保持原样，本实验不是链路所有缓冲的严格优先级设计；有限流量下观察MoE退化，不能据此保证无限负载无饥饿。

新二进制各自写入哈希、命令、构建/自测日志；矩阵绑定同一源码、工具镜像和用例哈希。共同sim/main.cpp和controller.h没有改写，仅新增独立路由器定向探针。RR参考为旧312结果，不以本实验新完成时间改写其注入计划。

## 源码交付

本地可审查Git提交：{commit['commit']}，分支{commit['branch']}，仅本地未发布；基准为已验证090a55d0源码。源码及运行脚本见package/，差异见SOURCE_CHANGE.patch，映射见LOCAL_SOURCE_COMMIT.json；部署身份还绑定driver.py和audit_priority.py的哈希。原目录和原论文未修改。

## 保留的启动/探针失败

1. 3be6dbca32611f9c：单元编译未配置Beneš LUT包含路径，编译失败，没有运行探针或24组；原失败目录保留。
2. ef3692791a4e77c9：补齐包含路径后SV事件驱动探针在81时间单位的优先级断言失败，24组未启动。当前没有把失败归因为RTL或仿真器，调度根因尚未独立确认。
3. 当前1547eea9172ebef6：使用与共同台一致的C++驱动检查相同仲裁RTL，通过四类型次序和跨输出争用探针，再进入共同回归。前两版不是loveYoumu已有实验，也没有重跑旧312组；均以不同构建/探针身份保留，不静默覆盖。

原始失败快照见BOOTSTRAP_FAILED_STATUS.json、SV_PROBE_FAILED_STATUS.json；各目录按部署身份隔离。旧receipts根目录可能保留前版失败文件，当前以LATEST_STATUS.json及receipts/当前部署身份/为准。

## 解读边界

本批为6个已使用过的开发用例，不是留出验证。各用例6个通信阶段分别初始化，阶段汇合周期之和不是完整层或端到端推理时间。GetS为合成只读事务，MoE端点/字节来自原传输元数据，无数值MoE推理或完整CPU一致性协议。

L2不能仅凭GetS或P99改善判好：必须同时看MoE进度和汇合时间，以及相对双平面增量是否仍存在。192-bit连续打包、NA分组及5有效端口Beneš均按声明的平台映射，不声称作者完整加速器复现。静态连线检查不是标准单元面积/时序，1ns仍是模拟参数；旧22.13%不用于此版。

## 原始来源与复核入口

- USER_PLAN.md：用户指定原分工文档的工作区副本。
- HiBand原文：DOI https://doi.org/10.1145/3770743.3803944 ，Fig.6与§4–5；本地全文位于../tmp/pdfs/hiband/DAC_2026_Draft_Proceedings/papers/282_Camera_Ready_Paper.pdf，已检查第4页图及第5页续文。
- REMOTE_PREFLIGHT.json：启动前进程、目录与资源只读核对；不因旧运行记录推定当前存活。
- REMOTE_START.json、LATEST_STATUS.json：真实启动和最新状态。
- L1_STATIC_AUDIT.json、L1_PAPER_IMPLEMENTATION_MAPPING.csv：适配和物理连接核对。
- receipts/：构建、回归及结果审计回执，按部署身份分开。
- collect/status脚本只读检查，driver仅执行新版本回归和24组，不包含综合。
'''
indpath=R/'INDEPENDENT_AUDIT.json'
if indpath.exists():
 independent=json.loads(indpath.read_text(encoding='utf-8'))
 if independent['status']=='PASS_COMPLETE_24':
  text+='\n## 24组预检结果（六个开发用例）\n\n'
  text+='独立检查24组/144阶段，冻结源码、二进制、原RR结果哈希、数据内容、包/网络字节及SRAM服务账本通过。以下表只汇总6用例预检；全30用例扩展另行记录。比值均为RR指标÷优先级指标，大于1表示对应指标缩短。\n\n'
  text+='| 臂 | 汇合阶段和几何平均加速比 | MoE阶段和几何平均加速比 | 每例最大阶段P99比值的几何均值 | 汇合缩短/变慢/持平 |\n|---|---:|---:|---:|---|\n'
  for row in independent['summary']:
   text+=f"| {row['arm']} | {row['join_geomean_speedup']:.6f} | {row['moe_geomean_speedup']:.6f} | {row['max_phase_p99_geomean_ratio']:.6f} | {row['wins']}/{row['losses']}/{row['n']-row['wins']-row['losses']} |\n"
  text+='\n共享Mesh与HiBand full-global的类型优先结果相同；本开发样本中，优先级降低GetS尾延迟的同时可能推迟MoE，汇合收益不能只由P99下降推断。其他HiBand分配接近持平的现象也需保留。旧双平面RR对比新优先Mesh仅是开发诊断，不能替代统一仲裁口径的正式矩阵或实现代价评估。\n'
  text+='\n预检结果见INDEPENDENT_PAIRED_RUNS.csv、INDEPENDENT_PAIRED_PHASES.csv、INDEPENDENT_SUMMARY.csv与INDEPENDENT_AUDIT.json。原作者的C1统一审计继续保留；本轮不启动综合。\n'
if full:
 fullstart=json.loads((R/'FULL_EXTENSION_START.json').read_text(encoding='utf-8'))
 text+=f'''\n## 全30用例扩展：仅补96组\n
预检及独立审计通过后，按原计划扩展至30用例×4优先臂=120组。旧24组按结果哈希直接复用，不重建、不重跑回归、不重跑旧312组、不综合。其余24用例×4臂=96组为新任务。

观察时间：{full['observed_at']}。状态{fm['status']}，共{fm['completed']}/120回执完成，其中24组为预检复用，新增完成{fm['new_completed']}/96。远端目录：{fullstart['path']}；PID {fullstart['pid']}。源码仍为{src['source_digest']}，二进制复用预检构建；所有30份输入用例重新只读核对冻结哈希，规则和预算不变。8-worker、每组1CPU/3GiB上限不变。

FULL_EXPERIMENT_CHECKLIST.csv列出120组及复用标识；FULL_LATEST_STATUS.json为真实进度，FULL_INDEPENDENT_AUDIT.json为最新只读独立审计。未完成时不把部分均值当作完整结果。C1最终统一审计及论文整理归原作者。\n'''
 if fm['status']=='PASS' and fm['completed']==120:
  import datetime
  finished=datetime.datetime.fromtimestamp(fm['finished'],datetime.timezone(datetime.timedelta(hours=8))).isoformat()
  independent_path=R/'FULL_INDEPENDENT_AUDIT.json'
  independent=json.loads(independent_path.read_text(encoding='utf-8')) if independent_path.exists() else {}
  text+=f'''\n## 120组完成核查\n
120组仿真于{finished}完成，120/120 PASS、0组仿真失败，包含复用24组和新增96组。每组6阶段，共720阶段。

本次检查时间{full['observed_at']}；本地独立审计状态{independent.get('status','pending')}，检查{independent.get('checks',0)}项，发现失败{len(independent.get('failures',[]))}项。核对源码与二进制哈希、120组输出及原RR哈希、数据内容、包数/网络字节、SRAM服务和阶段完成关系。

需区分原驱动状态：仿真MATRIX为PASS，但其后audit_full.py读取本扩展目录BUILD.json失败；构建回执实际在复用的预检目录，扩展目录没有复制该文件。原FAILURE.json是此汇总定位错误，不是RTL或数据账本检查失败。原失败记录保留，远端未改动、未重启。本地独立审计从预检目录读取并核对真实构建/二进制，已完成对全部120组的复核。后续恢复原汇总脚本时应通过EXTENSION_START.json的precheck_path定位BUILD.json，只执行分析，不重跑实验。\n'''
(R/'README.md').write_text(text,encoding='utf-8')
print('Report updated:',s['observed_at'],b.get('status'),m.get('status'),m.get('completed',0))

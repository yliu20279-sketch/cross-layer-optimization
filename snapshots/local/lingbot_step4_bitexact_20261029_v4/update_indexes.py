from pathlib import Path
entries={
'AGENTS.md':'2026-10-30 LingBot[步骤4数值修复](lingbot_step4_bitexact_20261029_v4/REPORT.md)：原混合BF16/FP32、host128/HB8、目标GPU0。197738个rsqrt因子/404967424个postnorm元素、全序列12655232 logits与scores/98869行Top8/790952权重、全K/V404967424元素均对原GPU逐位一致；5路交错split-K、FDA16、Flash UNFUSE_FMA及原O bias精度边界修复。双CFG各64行串联attention→自主router/MoE→层输出10项1310720元素通过，67独立检查/12负对照、192载荷本地SHA通过。旧数学/GEMM/attention及遗漏bias失败保留。完整98869查询的单层CPU验收已在113独立后台启动，16线程/nice10/12小时上限、断点及首差即停，完成后独立复核；当前仍PARTIAL，不能把64行写成完整层或TI2V通过。16GiB EX2+64MiB RSQ指令域表是模型无关host软件兼容数据，另32MiB失败RCP候选保留，静态余约11.03GiB，访问/分页时序未认证。新增7次有界外部GPU参考、完整模型调用0；新目标原生0，LingBot累计旧原生1/物理0，无策略收益。\n\n',
'project_maintenance/ASSETS.md':'2026-10-30 LingBot[原精度CPU数值适配v4](../lingbot_step4_bitexact_20261029_v4/REPORT.md)：rsqrt/exp、自主router全序列、完整K/V及双CFG各64查询的完整上下文串联层输出逐位通过；67独立检查/12负对照，compact review192载荷33678282B/外包16577082B本地SHA通过，大型数学域表/全KV留113。全98869查询单层验收后台进行，尚未完成，整体PARTIAL；旧失败保留，原BF16/FP32、host128/HB8、目标GPU0，新原生0/物理0。数学表host开销另计，非目标时序或HiBand/Sem-MoE收益认证。\n\n',
'project_maintenance/CONVERSATIONS.md':'2026-10-30 本LingBot专责继续步骤4：[v4报告](../lingbot_step4_bitexact_20261029_v4/REPORT.md)记录GPU数学域表的CPU兼容、router5路交错split-K与BF16 FDA16、Flash非融合乘减/FP32除法及O bias修复；双CFG各64行从输入到层输出无Golden中间注入逐位通过，67检查/12负对照及192载荷本地SHA通过。用户原无GPU/混合BF16-FP32/host128-HB8约束保持，未放宽门槛，旧失败保留。113已启动全98869查询单层验收与后续独立审计，仍PARTIAL，当前不称完整层通过；7外部GPU诊断/完整模型0，新目标原生0，LingBot历史1/物理0。未推进SWE任务或性能矩阵。\n\n'
}
for name,entry in entries.items():
 p=Path(name);s=p.read_text(encoding='utf-8-sig');first,rest=s.split('\n',1);assert 'lingbot_step4_bitexact_20261029_v4/REPORT.md' not in s[:1800];p.write_text(first+'\n\n'+entry+rest.lstrip('\n'),encoding='utf-8')
print('updated 3 indexes; existing content preserved')

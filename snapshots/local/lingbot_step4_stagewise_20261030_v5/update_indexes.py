from pathlib import Path
entries={
'AGENTS.md':'2026-10-30 LingBot[步骤4稀疏专家修复/两阶段恢复](lingbot_step4_stagewise_20261030_v5/REPORT.md)：旧全查询在条件分支11776行后FFN4元素差异停止，失败保留。源专家28批量148的gate/up为6路split-K/FP32工作区；完整227328元素与GPU逐位一致，原失败64行FFN4→0（隔离诊断）。形状目录498项非498数值PASS，M142同核仍待全层门；SiLU全部有限BF16域一致。本轮3次有界外部GPU参考/完整模型0，累计v4-v5外部10；目标GPU0/新目标原生0/LingBot旧原生1/物理0。1660断点检查及4新负对照通过；仅复用11776行attention/FFN输入，旧专家输出不晋级。新流程先自主生成全部FFN输入再路由分组执行真实批量，113独立后台16线程/nice10/12小时上限并自动独立审计，仍PARTIAL；原BF16-FP32/host128/HB8与旧失败不改。41载荷8396965B复核包本地归档SHA通过；两次源码审批超时已由具体3882B包授权解决，当前无待审批项。\n\n',
'project_maintenance/ASSETS.md':'2026-10-30 LingBot[稀疏专家split-K恢复](../lingbot_step4_stagewise_20261030_v5/REPORT.md)：旧4差异定位为M148专家gate/up的并行6分区，完整227328元素及原失败131072元素FFN修复通过，仍为隔离合同。新两阶段全98869查询后台验收：A生成完整FFN输入，B自主全路由批量；11776行A资产复用经1660检查，旧B不复用；全层仍PARTIAL，原精度/host128-HB8/目标GPU0保持。41载荷8396965B/归档3931657B本地SHA通过，大载荷留113；未新增目标原生或收益。\n\n',
'project_maintenance/CONVERSATIONS.md':'2026-10-30 LingBot继续步骤4：[v5续作](../lingbot_step4_stagewise_20261030_v5/REPORT.md)确认旧全量在11776行后因FFN4个BF16差异停止，不是下载故障。外部原批量专家诊断定位M148的6路split-K；CPU完整gate/up及失败FFN修复逐位通过，SiLU有限BF16域一致。用户明确批准具体3882B包后上传与有界诊断完成，先前审批超时不再是当前阻断。新两阶段CPU验收先完成全attention/FFN输入，再按自主路由真实批量执行专家，1660复用检查/4负对照通过；仅复用A、保留旧B失败。后台无本机连接依赖，原混合精度/host128-HB8/目标GPU0，新目标原生0/物理0，全层仍PARTIAL。41载荷本地归档SHA通过，未接管SWE或性能矩阵。\n\n'
}
for name,entry in entries.items():
 p=Path(name);s=p.read_text(encoding='utf-8-sig');first,rest=s.split('\n',1);assert 'lingbot_step4_stagewise_20261030_v5/REPORT.md' not in s[:2000];p.write_text(first+'\n\n'+entry+rest.lstrip('\n'),encoding='utf-8')
print('updated own followup entries in 3 indexes, other content retained')

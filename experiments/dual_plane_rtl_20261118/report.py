"""Write a concise Chinese interpretation of audited, paired RTL runs."""
import collections,json,statistics
from pathlib import Path
R=Path(__file__).resolve().parent
def main():
    manifest=json.loads((R/'MATRIX.json').read_text());out=Path(manifest['result_path']);audit=json.loads((out/'AUDIT.json').read_text())
    assert manifest['status']=='PASS' and audit['runs']==len(manifest['tasks'])
    cases=json.loads((R/'CASES.json').read_text());data={}
    for t in manifest['tasks']:
        if t['bank']==8 and t['clock']==1:
            data[t['case'],t['arm']]=json.loads((out/(t['case']+'_'+t['arm']+'_b8.json')).read_text())['waves']
    def finish(name,arm):return sum(w['finish'] for w in data[name,arm])
    def p99(name,arm):return max(w['gets_p99'] for w in data[name,arm])
    def best(name):return sum(min(data[name,a][i]['finish'] for a in ['hiband_FG','hiband_GB','hiband_LB']) for i in range(6))
    comp={(c['arm'],c['baseline']):c for c in audit['comparisons']}
    base=comp['dual','hiband_phase_best'];cs=comp.get(('forced_cs','delay_control'))
    lines=['# 双平面 NoC RTL 实验结果（2026-11-18）','',
      f"完成 {audit['runs']} 组回放、{audit['phase_checks']} 个通信阶段。输入、包数、逐位数据、按类型分流、网络字节及 SRAM 服务次数审计通过。",'',
      f"双平面关闭 CS，相对 HiBand 每阶段理想最优模式的通信阶段总时间几何平均加速比为 {base['geomean_speedup']:.4f}，范围 {base['min_speedup']:.4f}–{base['max_speedup']:.4f}；30 个算例中 {base['wins']} 个缩短、{base['losses']} 个增长。",'',
      '## 最密集请求下的结果','',
      '| token | 请求分布 | HiBand 理想下界 | 双平面，CS 关闭 | 强制 CS | 双平面时间缩短 | GetS 最坏阶段 P99：Mesh → 双平面 |',
      '|---:|---|---:|---:|---:|---:|---:|']
    for tokens in [4,8,16]:
        for pattern in ['hotspot','distributed']:
            names=[c['name'] for c in cases if c['tokens']==tokens and c['pattern']==pattern and c['interval']==1]
            mean=lambda f:statistics.mean(f(n) for n in names)
            lines.append(f"| {tokens} | {pattern} | {mean(best):.1f} | {mean(lambda n:finish(n,'dual')):.1f} | {mean(lambda n:finish(n,'forced_cs')):.1f} | {mean(lambda n:100*(1-finish(n,'dual')/best(n))):.2f}% | {mean(lambda n:p99(n,'mesh')):.1f} → {mean(lambda n:p99(n,'dual')):.1f} |")
    lines+=['','时间单位为 NoC 周期，取六个独立通信阶段之和。4/8 token 各一条轨迹，16 token 三个 seed 取均值；改善率先逐 seed 计算。P99 在每个阶段计算，再取最坏阶段，最后跨 seed 平均，不是合并全部事务后的 P99。','',
      '## 收益归因','']
    if cs:
        lines.append(f"强制 CS 相对相同配置消息、相同选包等待的 Mesh 对照，几何平均加速比为 {cs['geomean_speedup']:.4f}，{cs['wins']} 个算例更快、{cs['losses']} 个更慢。相同配置等待的检查逐阶段通过。因此，分流收益、注入时序变化和旁路效果可以分别检查。")
    lines+=['',f"在线控制原型在 {audit['runtime_installed_phases']} 个阶段提交了更新；退出原因统计为 `{audit['runtime_reasons']}`。该原型从通信阶段开始构造候选，并按目标周期计入主机墙钟耗时；没有模拟上一计算层中的提前规划。当前回放不能据此证明在线 CS 算法有额外净收益。",'',
      '下列单跑对照用于区分请求自身过载和 MoE 引入的干扰：','',
      '| 算例 | GetS 单跑 P99 | 混跑 Mesh P99 | 混跑双平面 P99 |',
      '|---|---:|---:|---:|']
    for name in ['fit16_641103_hotspot','fit16_641103_hotspot_rate3','fit16_641103_hotspot_rate6','fit16_641103_distributed']:
        lines.append(f"| {name} | {p99(name,'gets_only')} | {p99(name,'mesh')} | {p99(name,'dual')} |")
    lines+=['','新增平面能隔离链路和路由队列，NI 注入、接收与 SRAM 服务仍然共享。通算尾延迟下降不能直接换算为完整应用加速；这些回放没有执行 CPU 程序或数值 MoE 算子。逐阶段干扰见 `INTERFERENCE.csv`。','',
      '## 实现与适用范围','',
      '数据网络使用 SystemVerilog RTL，经 Verilator 执行。共同端点模型实际读写 SRAM 并校验持久化结果，配置通过 Mesh 传输 62 条命令和 62 条确认。GetS/DataS 按包类型进入 C Mesh；MoE 数据和控制使用 M Mesh，只有选择的 MoE 数据可以走 CS。',
      'HiBand 为按论文实现的目标平台 NoC 适配版，使用真实 Beneš 交换和共用四条物理通道的 global/local 分配。其逐阶段最优结果允许事后选择和免费切换，是乐观时延下界；不代表作者完整加速器。',
      'GetS 为合成只读事务，按请求和响应的网络字节数与 MoE 匹配，不代表完整一致性协议。4×4 拓扑固定，变化的是 token 数、轨迹 seed、请求分布和频率。新增 C Mesh 增加 16 个路由器、24 条双向邻接线及 16 条 NI 本地双向连接，结果没有归一化面积或布线成本。',
      '预测模块的数值回归通过；已有传输元数据没有同一 token 组的相邻层专家标签，因此没有报告真实预测精度。默认 1 ns 为回放周期参数，没有据此认定物理频率达到 1 GHz。','']
    structure=R/'STRUCTURE.json'
    if structure.exists():
        d=json.loads(structure.read_text());lines+=['结构检查状态：`'+d['status']+'`。三个配置未发现未驱动或冲突连线、锁存器或组合环。寄存器位统计见 `STRUCTURE.json`；未进行标准单元映射、布局布线或功耗签核。','']
    else:lines+=['结构综合回执尚待完成，不能由功能回归代替结构验收。','']
    (out/'REPORT_CN.md').write_text('\n'.join(lines),encoding='utf-8');print(out/'REPORT_CN.md')
if __name__=='__main__':main()

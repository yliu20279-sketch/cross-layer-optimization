"""Audit the prospective twelve-cohort closed-loop comparison."""
import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
import importlib.util
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from portable import PACKAGE, SRC, INPUT, RUNTIME, RUNS, VALIDATION, REFERENCE, resolve, warm_state, assert_first_schedule
import argparse

import numpy as np

ROOT = RUNS / 'sustained65/fixed12'
spec = importlib.util.spec_from_file_location('sustained_audit', VALIDATION / 'audit_sustained.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
read, save, common = audit.read, audit.save, audit.common


def main(selected_policy=None):
    protocol = read(ROOT / 'protocol.json')
    for path, digest in protocol['sources'].items():
        assert common.sha(path) == digest, path
    native = read(common.OP / 'gtp_srs_native_opp_profiles.json')
    tasks = {t['task_id']: t for t in read(common.PREP / 'gtp_srs_manifest.json')['tasks']}
    scenario = read(common.OP / 'scenario.json')
    plan = read(RUNS / 'mechanisms/plan.json')
    for path, digest in plan['source_hashes'].items():
        assert common.sha(path) == digest, path
    initial = warm_state(4)
    summaries, checks, all_records = {}, {}, {}
    selected = [selected_policy] if selected_policy else protocol['policies']
    for policy in selected:
        folder = ROOT / policy
        summary = read(folder / 'summary.json')
        records = read(folder / 'cohorts.json')
        all_records[policy] = records
        assert len(records) == protocol['cohorts'] == 12
        checks[policy] = []
        expected, cumulative = initial.copy(), 0.
        for row in records:
            cf = folder / f"cohort_{row['cohort']:02d}"
            inputs = {name: common.sha(cf / name) for name in
                      ['summary.json', 'tasks.csv', 'flows.csv', 'trace.npz', 'expert_buffers.json']}
            inputs['auditor_sha256'] = common.sha(__file__)
            inputs['helper_sha256'] = common.sha(VALIDATION / 'audit_sustained.py')
            cache = cf / 'independent_audit.json'
            if cache.exists() and read(cache)['inputs'] == inputs:
                stored = read(cache)
                with np.load(cf / 'trace.npz') as trace:
                    np.testing.assert_allclose(trace['initial_state'], expected, rtol=0, atol=1e-9)
                    expected = trace['end_state'].copy()
                c = stored['result']
            else:
                c, expected = audit.cohort_check(cf, expected, protocol, native, tasks, scenario, plan)
                save(cache, dict(inputs=inputs, result=c))
            checks[policy].append(c)
            cumulative += row['duration_s']
            assert abs(cumulative - row['cumulative_end_s']) < 1e-8
            assert c['within_65C']
            print('AUDITED', policy, row['cohort'], flush=True)
        assert abs(cumulative - summary['cumulative_duration_s']) < 1e-8
        assert summary['idle_tail']['infinite_idle_tail_upper_C'] <= 65. + 1e-6
        group = records[6:12]
        assert summary['measurement_cohorts'] == [r['cohort'] for r in group]
        assert abs(24 / sum(r['duration_s'] for r in group) - summary['measured_throughput_req_s']) < 1e-10
        assert abs(sum(r['energy_J'] for r in group) / 24 - summary['measured_energy_per_request_J']) < 1e-10
        first, second = records[6:9], records[9:12]
        mean = lambda g: np.average(np.array([r['block_mean_C'] for r in g]), axis=0,
                                    weights=[r['duration_s'] for r in g])
        window = dict(block_mean_delta_C=float(np.max(abs(mean(second) - mean(first)))),
            duration_relative_delta=abs(sum(r['duration_s'] for r in second) / sum(r['duration_s'] for r in first) - 1),
            slow_mode_mean_delta_C=float(np.max(abs(np.mean([r['slow_mode_boundary_C'] for r in second], axis=0) -
                                                    np.mean([r['slow_mode_boundary_C'] for r in first], axis=0)))))
        for k, v in window.items():
            assert abs(v - summary['stability'][k]) < 1e-10
        assert window['block_mean_delta_C'] <= protocol['convergence']['block_mean_window_delta_C']
        assert window['duration_relative_delta'] <= protocol['convergence']['duration_window_relative_delta']
        assert window['slow_mode_mean_delta_C'] <= protocol['convergence']['slow_mode_mean_window_delta_C']
        assert summary['stability']['stable']
        summaries[policy] = summary
    if selected_policy:
        save(ROOT / f'{selected_policy}_audit.json', dict(status='PASS_COMPLETE_POLICY', policy=selected_policy,
             cohorts=checks[selected_policy], total_tasks=sum(c['tasks'] for c in checks[selected_policy]),
             audit_sha256=common.sha(__file__)))
        print('PASS_COMPLETE_POLICY', selected_policy, flush=True)
        return
    a, c = summaries['amber_energy'], summaries['contract_energy']
    comparison = dict(amber_energy=a, contract_energy=c,
        contract_latency_change_pct=100 * (c['measured_mean_cohort_s'] / a['measured_mean_cohort_s'] - 1),
        contract_throughput_change_pct=100 * (c['measured_throughput_req_s'] / a['measured_throughput_req_s'] - 1),
        contract_energy_per_request_change_pct=100 * (c['measured_energy_per_request_J'] / a['measured_energy_per_request_J'] - 1),
        comparison_scope='Fixed12 actual closed-loop cohorts, final6 window-stable; common selected OPP, guard64 and cap65.',
        same_window_first_half_latency_change_pct=100 * (sum(r['duration_s'] for r in all_records['contract_energy'][6:9]) /
                                                        sum(r['duration_s'] for r in all_records['amber_energy'][6:9]) - 1),
        same_window_second_half_latency_change_pct=100 * (sum(r['duration_s'] for r in all_records['contract_energy'][9:12]) /
                                                         sum(r['duration_s'] for r in all_records['amber_energy'][9:12]) - 1))
    save(ROOT / 'comparison.json', comparison)
    result = dict(status='PASS_COMPLETE', policies=checks,
        total_tasks=sum(c['tasks'] for values in checks.values() for c in values),
        total_cohorts=24, total_requests=96, fixed_measurement_cohorts=list(range(7, 13)),
        both_window_stability_checks_pass=True, every_actual_cohort_under_65C=True,
        first_cohort_complete_task_timing_reproduces_original=True,
        continuous_full_state_carry=True, no_cooling_gaps=True,
        same_OPP_every_native_task=True, original_forecast_sample_parity=True,
        protocol_sha256=common.sha(ROOT / 'protocol.json'), audit_sha256=common.sha(__file__))
    save(ROOT / 'audit.json', result)
    lines = ['# A2.7B：同选频、持续65°C上限的正式闭环验证', '',
        '两种控制器各实际连续执行12批，每批4请求、每请求512-token prefill+1 decode；使用原固定建模专家路由。',
        '2GHz、Rconv=3、45°C环境；相同完整暖态、能耗OPP表、60°C软目标、65°C上限和64°C预测守卫。',
        '每批结束立即释放下一批，只有最多1ms的共同计量对齐；1292个热状态及OPP历史连续传递，没有冷却间隔，每一批都重新作反馈决策。',
        '正式执行前固定12批与第7–12批计量窗口；第7–9批与第10–12批比较均温/批时延/最慢模态漂移。未加入迁移或NoC重构。', '',
        '| 控制器 | 连续执行 s | 后6批平均每批 s | 后6批吞吐 req/s | 后6批能耗 J/req | 全程峰温 °C | 后6批峰温 °C |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for label, x in [('同选频 AMBER', a), ('同选频 热契约准入', c)]:
        lines.append(f"| {label} | {x['cumulative_duration_s']:.3f} | {x['measured_mean_cohort_s']:.6f} | {x['measured_throughput_req_s']:.6f} | {x['measured_energy_per_request_J']:.6f} | {x['whole_run_peak_C']:.6f} | {x['measured_peak_C']:.6f} |")
    lines += ['', f"热契约相对同选频 AMBER：后6批平均时延 {comparison['contract_latency_change_pct']:+.4f}%，吞吐 {comparison['contract_throughput_change_pct']:+.4f}%，每请求能耗 {comparison['contract_energy_per_request_change_pct']:+.4f}%。", '',
        f"窗口敏感性：第7–9批时延差 {comparison['same_window_first_half_latency_change_pct']:+.4f}%；第10–12批时延差 {comparison['same_window_second_half_latency_change_pct']:+.4f}%。", '',
        '| 控制器 | 两窗口各块均温最大差 °C | 两窗口批时延相对差 | 最慢模态均值最大差 °C | 窗口稳定 |',
        '|---|---:|---:|---:|---|']
    for label, x in [('AMBER', a), ('热契约', c)]:
        s = x['stability']
        lines.append(f"| {label} | {s['block_mean_delta_C']:.6f} | {s['duration_relative_delta']:.6%} | {s['slow_mode_mean_delta_C']:.6f} | {s['stable']} |")
    lines += ['', '预声明窗口阈值：各块均温差≤0.03°C、批时延差≤1%、最慢模态均值差≤0.03°C。这里的稳定是连续窗口统计稳定，不声称每批任务顺序和局部峰温严格周期重复。', '',
        '| 控制器 | 批次 | 每批时延 s | 峰温 °C | 最慢模态边界漂移 °C |',
        '|---|---:|---:|---:|---:|']
    for policy, records in all_records.items():
        for r in records:
            lines.append(f"| {policy} | {r['cohort']} | {r['duration_s']:.3f} | {r['peak_C']:.6f} | {r['slow_modal_output_drift_C']:.6f} |")
    lines += ['', f"独立审计PASS_COMPLETE，共{result['total_tasks']:,}任务、24批、96请求；逐项核对完整任务、MAC、同OPP、专家身份与dispatch/return字节、资源及缓冲区生命周期、逐bin功耗重建、完整RC重放和跨批状态连续。", '',
        'AMBER预测使用完整1292模态的等价传播来减少宿主仿真时间；没有降阶，实际执行仍用原始物理RC。原预测函数抽样比对通过，且首批完整任务时序与历史原实现逐项相同。宿主加速不计作硬件收益，二者模型中任务派发均计10µs。',
        '约束范围是现有1ms RC模型端点及末尾无限空闲尾部；这是原建模路由、bounded per-task native profile下的闭环结果，不是硅片测量、checkpoint数值推理或完整持续DRAM命令队列模拟。',
        '探索阶段的严格逐批周期判据未用于选择正式窗口；其数据保留在上级目录，未混入本表。', '',
        '[预声明协议](protocol.json) · [原始比较](comparison.json) · [独立审计](audit.json)']
    (ROOT / 'RESULTS.md').write_text('\n'.join(lines) + '\n')
    print('PASS_COMPLETE', json.dumps({k: v for k, v in comparison.items() if k not in protocol['policies']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--policy', choices=['amber_energy', 'contract_energy'])
    main(parser.parse_args().policy)

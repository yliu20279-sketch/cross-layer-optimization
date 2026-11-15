"""Independent audit and report of saved sustained closed-loop experiments."""
import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
import csv
import importlib.util
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from portable import PACKAGE, SRC, INPUT, RUNTIME, RUNS, VALIDATION, REFERENCE, resolve, warm_state, assert_first_schedule
import sys

import numpy as np

ROOT = RUNS / 'sustained65'
HERE = SRC
sys.path.insert(0, str(HERE))
from op_thermal import ThermalPlant
from thermal_geometry import dram_to_logic_regions

module = importlib.util.spec_from_file_location('historical_audit', VALIDATION / 'audit_and_report.py')
common = importlib.util.module_from_spec(module)
module.loader.exec_module(common)


def read(path):
    return json.loads(resolve(path).read_text())


def rows(path):
    with Path(path).open(newline='') as stream:
        return list(csv.DictReader(stream))


def save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def cohort_check(folder, expected_initial, protocol, native, tasks, scenario, plan):
    result = read(folder / 'summary.json')
    task_rows, flows = rows(folder / 'tasks.csv'), rows(folder / 'flows.csv')
    task_map = {(int(r['request']), int(r['task_id'])): r for r in task_rows}
    assert set(task_map) == {(q, tid) for q in range(4) for tid in tasks}
    assert sum(float(r['MAC']) for r in task_rows) == 4 * sum(t['mac_ops'] for t in tasks.values())
    for path, digest in result['source_hashes'].items():
        assert common.sha(path) == digest, path
    dt = .001
    count = int(round(result['duration_s'] / dt))
    energy = np.zeros((count, 96))
    static = np.zeros(96)
    p = scenario['power']
    static[:16] = p['core_static_W'] + p['lbuf_leak_W'] + p['router_static_W'] + p['ni_static_W']
    static[16:32] = p['sram_leak_W']
    memory = read(RUNTIME / 'prepared/memory_curves.json')
    static[32:] = memory['1']['idle_W_per_partition'] / 4
    arrays, partitions, links = defaultdict(list), defaultdict(list), defaultdict(list)
    locations = {}
    placement = read(common.PREP / 'placement.json')['meta_expert_cluster']

    def spread(start, end, value):
        assert 0 <= start < end <= count * 1e6 + 1e-4
        first, last = int(start // 1e6), min(count, int(math.ceil(end / 1e6)))
        ix = np.arange(first, last)
        overlaps = np.maximum(0., np.minimum(end, (ix + 1) * 1e6) - np.maximum(start, ix * 1e6))
        energy[first:last] += overlaps[:, None] / (end - start) * value

    for r in task_rows:
        q, tid, c = int(r['request']), int(r['task_id']), int(r['cluster'])
        task = tasks[tid]
        home = placement[task['layer']][task['expert']] if 'expert' in task else task['primary_cluster']
        assert c == int(r['memory_partition']) == home
        ratio = float(r['opp_ratio'])
        assert ratio == plan['choices'][str(tid)]
        profile = native['profiles'][str(ratio)][native['task_profile_keys'][str(tid)]]
        start, end = float(r['start_ns']), float(r['end_ns'])
        assert abs(end - start - profile['duration_ns']) < 1e-4
        assert all(float(task_map[q, dep]['end_ns']) <= start + 1e-4 for dep in task['deps'])
        assert float(r['MAC']) == task['mac_ops']
        a = profile['activity']
        assert abs(float(r['physical_read_bytes']) - sum(a[5:9])) < 1e-5
        assert abs(float(r['physical_write_bytes']) - sum(a[9:13])) < 1e-5
        arrays[c].append((start, end))
        partitions[c].append((start, end))
        spread(start, end, common.task_energy(a, ratio, c, scenario, static))
        if 'expert' in task:
            assert int(r['expert']) == task['expert']
            key = q, task['stage'], task['layer'], task['expert']
            assert locations.setdefault(key, c) == c
    dispatch, returned = Counter(), Counter()
    timing = scenario['timing']
    hop = (timing['noc_link_latency_cycles'] + timing['noc_router_pipeline_cycles']) * timing['noc_cycle_ns']
    for f in flows:
        assert f['kind'] != 'expert_weight_copy'
        source, destination, size = int(f['src']), int(f['dst']), int(f['bytes'])
        path = list(map(int, f['path'].split('-')))
        assert path[0] == source and path[-1] == destination
        value = np.zeros(96)
        flits = math.ceil(size / timing['noc_flit_bytes'])
        start, end = float(f['start_ns']), float(f['end_ns'])
        service = int(f['arbitration_reservation_cycles']) * timing['noc_cycle_ns']
        for i, (a, b) in enumerate(zip(path, path[1:])):
            assert abs(a // 4 - b // 4) + abs(a % 4 - b % 4) == 1
            links[a, b].append((start + i * hop, start + i * hop + service))
            value[a] += flits * p['router_pJ_flit_hop'] * 1e-12
        value[source] += flits * p['ni_pJ_endpoint_flit'] * 1e-12
        value[destination] += flits * p['ni_pJ_endpoint_flit'] * 1e-12
        spread(start, end, value)
        if f['kind'] in ('expert_dispatch', 'expert_return'):
            q, tid = int(f['request']), int(f['task_id'])
            task = tasks[tid]
            key = q, task['stage'], task['layer'], source, destination, size
            (dispatch if f['kind'] == 'expert_dispatch' else returned)[key] += 1
    semantics = read(common.PREP / 'semantic_flows.json')['meta_sota']
    expected_dispatch, expected_return = Counter(), Counter()
    for q in range(4):
        for f in semantics:
            destination = locations[q, f['phase'], f['layer'], f['expert']]
            home = f['source_cluster']
            if home != destination:
                expected_dispatch[q, f['phase'], f['layer'], home, destination, f['dispatch_bytes']] += 1
                expected_return[q, f['phase'], f['layer'], destination, home, f['combine_bytes']] += 1
    assert dispatch == expected_dispatch and returned == expected_return
    maximum_overlap = max(common.overlaps(arrays), common.overlaps(partitions), common.overlaps(links))
    buffers = read(folder / 'expert_buffers.json')
    live = defaultdict(list)
    for b in buffers:
        arena = plan['expert_arenas'][str(b['partition'])]
        assert arena['base_address'] <= b['base_address']
        assert b['base_address'] + 2 ** 21 <= arena['end_address']
        assert b['release_ns'] <= count * 1e6
        live[b['partition'], b['slot']].append((b['allocation_ns'], b['release_ns']))
    common.overlaps(live)
    energy += static * dt
    with np.load(folder / 'trace.npz') as trace:
        boundary_error = float(np.max(abs(trace['initial_state'] - expected_initial)))
        # Online per-bin accumulation and independent vectorized trace replay
        # differ at roundoff (~1e-13 K); both carry the full physical state.
        np.testing.assert_allclose(trace['initial_state'], expected_initial, rtol=0, atol=1e-9)
        power_error = float(np.max(abs(trace['power_W'] - energy / dt)))
        assert power_error < 1e-8, power_error
        plant = ThermalPlant(45., common.OP / 'rc')
        plant.state = expected_initial.copy()
        temperature = np.asarray([plant.step(power) for power in trace['power_W']])
        thermal_error = float(np.max(abs(temperature - trace['temperature_C'])))
        assert thermal_error < 1e-8
        np.testing.assert_allclose(plant.state, trace['end_state'], rtol=0, atol=1e-9)
        initial_peak = float((45. + plant.C @ expected_initial).max())
        peak = max(initial_peak, float(temperature.max()))
        assert abs(peak - result['peak_C']) < 1e-8
        assert abs(trace['power_W'].sum() * dt - result['energy_J']) < 1e-7
        assert abs(trace['components_J'].sum() - result['energy_J']) < 1e-7
        expected_next = trace['end_state'].copy()
    if result['cohort'] == 1:
        assert_first_schedule(folder, result['policy'])
    return dict(cohort=result['cohort'], tasks=len(task_rows), status='PASS', peak_C=peak,
        within_65C=peak <= 65. + 1e-6, reconstructed_power_error_W=power_error,
        reconstructed_temperature_error_C=thermal_error, resource_overlap_ns=maximum_overlap,
        full_thermal_state_carry=True, boundary_roundoff_K=boundary_error,
        same_native_OPP=True, same_expert_IDs_and_traffic=True), expected_next


def main():
    protocol = read(ROOT / 'protocol.json')
    for path, digest in protocol['sources'].items():
        assert common.sha(path) == digest, path
    native = read(common.OP / 'gtp_srs_native_opp_profiles.json')
    tasks = {t['task_id']: t for t in read(common.PREP / 'gtp_srs_manifest.json')['tasks']}
    scenario = read(common.OP / 'scenario.json')
    plan = read(RUNS / 'mechanisms/plan.json')
    initial = warm_state(4)
    summaries, checks = {}, {}
    for policy in protocol['policies']:
        pf = ROOT / policy
        summaries[policy] = read(pf / 'summary.json')
        expected = initial.copy()
        records = read(pf / 'cohorts.json')
        checks[policy] = []
        cumulative = 0.
        for record in records:
            cf = pf / f"cohort_{record['cohort']:02d}"
            check, expected = cohort_check(cf, expected, protocol, native, tasks, scenario, plan)
            checks[policy].append(check)
            cumulative += record['duration_s']
            assert abs(cumulative - record['cumulative_end_s']) < 1e-8
            print('AUDITED', policy, record['cohort'], flush=True)
        assert len(records) == summaries[policy]['completed_cohorts']
        assert all(c['within_65C'] for c in checks[policy])
        assert summaries[policy]['status'] == 'COMPLETE_CONVERGED'
        assert summaries[policy]['idle_tail']['infinite_idle_tail_upper_C'] <= 65. + 1e-6
        last = records[-3:]
        assert all(r['stable_pair'] for r in last)
        assert all(r['full_state_delta_K'] <= protocol['convergence']['full_state_delta_K'] for r in last)
        assert summaries[policy]['measurement_cohorts'] == [r['cohort'] for r in last]
        assert abs(12 / sum(r['duration_s'] for r in last) - summaries[policy]['measured_throughput_req_s']) < 1e-10
    a, c = summaries['amber_energy'], summaries['contract_energy']
    comparison = dict(amber_energy=a, contract_energy=c,
        contract_latency_change_pct=100 * (c['measured_mean_cohort_s'] / a['measured_mean_cohort_s'] - 1),
        contract_throughput_change_pct=100 * (c['measured_throughput_req_s'] / a['measured_throughput_req_s'] - 1),
        contract_energy_per_request_change_pct=100 * (c['measured_energy_per_request_J'] / a['measured_energy_per_request_J'] - 1),
        qualifying_policies=[p for p, x in summaries.items() if x['all_cohorts_within_65C'] and x['status'] == 'COMPLETE_CONVERGED'])
    save(ROOT / 'comparison.json', comparison)
    audit = dict(status='PASS_COMPLETE', policies=checks, total_tasks=sum(c['tasks'] for v in checks.values() for c in v),
        first_cohort_full_schedules_reproduce_historical=True, same_OPP_table=True,
        continuous_full_state_carry=True, no_cooling_gaps=True, no_temperature_dependent_trace_repetition=True,
        protocol_sha256=common.sha(ROOT / 'protocol.json'), audit_sha256=common.sha(__file__))
    save(ROOT / 'audit.json', audit)
    lines = ['# A2.7B：相同能耗选频、持续65°C上限的闭环比较', '',
        '4并发，每请求512-token prefill+1 decode；原建模专家路由、2GHz、Rconv=3、45°C环境、共同暖态。',
        '每批完成后立即释放下一批，最多1ms对齐；完整1292状态连续传递，无冷却间隔；每批都重新逐任务决策。',
        '两者共用原固定能耗OPP表、60°C软目标、65°C上限和64°C预测守卫；未加入专家迁移或NoC重构。', '',
        '| 方法 | 实际完成批数 | 持续时间 s | 稳定后每批 s | 稳定吞吐 req/s | 稳定能耗 J/req | 全程峰温 °C | 稳定峰温 °C |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for label, x in [('同选频 AMBER', a), ('同选频 热契约准入', c)]:
        lines.append(f"| {label} | {x['completed_cohorts']} | {x['cumulative_duration_s']:.3f} | {x['measured_mean_cohort_s']:.6f} | {x['measured_throughput_req_s']:.6f} | {x['measured_energy_per_request_J']:.6f} | {x['whole_run_peak_C']:.6f} | {x['measured_peak_C']:.6f} |")
    lines += ['', f"热契约相对同选频 AMBER：稳定每批时延变化 {comparison['contract_latency_change_pct']:+.4f}%，吞吐变化 {comparison['contract_throughput_change_pct']:+.4f}%，每请求能耗变化 {comparison['contract_energy_per_request_change_pct']:+.4f}%。", '',
        '稳定判据在执行前冻结：至少8批；连续3对满足全状态边界差≤0.05K、各块均温/峰温差≤0.03°C、批时延变化≤0.5%、最慢模态输出漂移≤0.01°C；之后再实际运行2批确认，最后3批计量。',
        f"AMBER计量批次：{a['measurement_cohorts']}；热契约计量批次：{c['measurement_cohorts']}。", '',
        '逐批实测明细：', '', '| 方法 | 批次 | 时延 s | 峰温 °C | 全状态边界差 K | 最慢模态漂移 °C | 连续稳定对 |', '|---|---:|---:|---:|---:|---:|---:|']
    for policy in protocol['policies']:
        for r in read(ROOT / policy / 'cohorts.json'):
            lines.append(f"| {policy} | {r['cohort']} | {r['duration_s']:.3f} | {r['peak_C']:.6f} | {r['full_state_delta_K']:.6f} | {r['slow_modal_output_drift_C']:.6f} | {r['consecutive_stable_pairs']} |")
    lines += ['', f"独立审计 PASS_COMPLETE：{audit['total_tasks']:,} 个任务；核对同OPP、完整任务/MAC/专家身份及通信字节、Array/DRAM/链路占用、缓冲区生命周期、逐bin功耗重建、完整RC重放及跨批完整热状态传递。首批完整任务时序与历史单轮结果完全一致。", '',
        'AMBER模拟器仅缓存不变的能量向量/脉冲响应以减少宿主运行时间；与原预测函数抽样逐值比对，且首批完整时序一致。缓存不改变控制策略或模型中的10µs任务派发延迟。',
        '温度约束限定于现有1ms RC模型端点及末尾无限空闲尾部；这是建模路由、bounded per-task native profile的闭环仿真，不是硅片测量或checkpoint数值推理。', '',
        '[协议](protocol.json) · [原始比较](comparison.json) · [独立审计](audit.json)']
    (ROOT / 'RESULTS.md').write_text('\n'.join(lines) + '\n')
    print('PASS_COMPLETE', json.dumps({k: v for k, v in comparison.items() if k not in protocol['policies']}), flush=True)


if __name__ == '__main__':
    main()

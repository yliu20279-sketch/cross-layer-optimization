"""Independent saved-record checks for the MoE mechanism campaign."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from portable import PACKAGE, SRC, INPUT, RUNTIME, RUNS, VALIDATION, REFERENCE, resolve, warm_state, assert_first_schedule
import sys

import numpy as np

ROOT = RUNS / 'mechanisms'
HERE = SRC
sys.path.insert(0, str(HERE))
from op_thermal import ThermalPlant
from thermal_geometry import dram_to_logic_regions

PREP = INPUT / 'prepared'
OP = PREP / 'operating_point_2ghz_rconv3'
REQUIRED = ('amber', 'amber_energy', 'contract_full', 'contract_energy', 'energy_none',
            'replica_control', 'replica_select', 'dynamic', 'dynamic_forced', 'dynamic_forced_control')
LABELS = dict(amber='AMBER', amber_energy='同能耗选频 AMBER', contract_full='全速＋热契约',
              contract_energy='路线A：能耗选频＋热契约', energy_none='仅能耗选频，无热准入',
              replica_control='付同样预复制，不选副本', replica_select='专家副本选择',
              dynamic='成本感知动态专家迁移', dynamic_copy_control='同运行时复制，不迁移',
              dynamic_forced='单专家付费迁移干预', dynamic_forced_control='同单次复制，不使用')


def read(path):
    return json.loads(resolve(path).read_text())


def sha(path):
    return hashlib.sha256(resolve(path).read_bytes()).hexdigest()


def csv_rows(path):
    with Path(path).open(newline='') as stream:
        return list(csv.DictReader(stream))


def bank_indices(partition):
    y, x = divmod(partition, 4)
    return [32 + (2 * y + j // 2) * 8 + 2 * x + j % 2 for j in range(4)]


def overlaps(groups):
    maximum = 0.
    for values in groups.values():
        values.sort()
        for a, b in zip(values, values[1:]):
            maximum = max(maximum, a[1] - b[0])
    assert maximum < 1e-4, maximum
    return maximum


def task_energy(activity, ratio, partition, scenario, static):
    p = scenario['power']
    result = np.zeros(96)
    voltage = {1.: 1., .75: .9, .5: .8}[ratio]
    result[partition] += activity[0] / (scenario['activity_model']['peak_fp16_MAC_per_cycle_per_cluster'] *
                           scenario['activity_model']['npu_frequency_Hz']) * p['core_dynamic_full_W'] * voltage ** 2
    result[partition] += (activity[3] * p['lbuf_read_pJ_access'] + activity[4] * p['lbuf_write_pJ_access']) * 1e-12
    result[partition] += sum(activity[5:13]) * 8 * p['hb_pJ_per_bit'] * 1e-12
    result[16 + partition] += (activity[1] * p['sram_read_pJ_access'] + activity[2] * p['sram_write_pJ_access']) * 1e-12
    b = bank_indices(partition)
    result[b] += np.maximum(0., np.asarray(activity[13:17]) - static[b] * activity[18] * 1e-9)
    return result


def audit_case(folder, plan, native, tasks, scenario, reference_work=None):
    result = read(folder / 'summary.json')
    for path, value in {**result['code_hashes'], **result['source_hashes']}.items():
        assert sha(path) == value, path
    rows, flows = csv_rows(folder / 'tasks.csv'), csv_rows(folder / 'flows.csv')
    copies = read(folder / 'copies.json')
    buffers = read(folder / 'expert_buffers.json')
    count = result['requests']
    by_task = {(int(r['request']), int(r['task_id'])): r for r in rows}
    assert set(by_task) == {(q, tid) for q in range(count) for tid in tasks}
    static = np.zeros(96)
    p = scenario['power']
    static[:16] = p['core_static_W'] + p['lbuf_leak_W'] + p['router_static_W'] + p['ni_static_W']
    static[16:32] = p['sram_leak_W']
    curves = read(RUNTIME / 'prepared/memory_curves.json')
    static[32:] = curves['1']['idle_W_per_partition'] / 4
    dynamic = np.zeros(96)
    arrays, partitions, links = defaultdict(list), defaultdict(list), defaultdict(list)
    work = {}
    selections = {}
    for row in rows:
        q, tid, c = int(row['request']), int(row['task_id']), int(row['cluster'])
        task = tasks[tid]
        assert c == int(row['memory_partition'])
        ratio = float(row['opp_ratio'])
        profile = native['profiles'][str(ratio)][native['task_profile_keys'][str(tid)]]
        activity = profile['activity']
        start, end = float(row['start_ns']), float(row['end_ns'])
        assert abs(end - start - profile['duration_ns']) < 1e-4
        assert all(float(by_task[q, dep]['end_ns']) <= start + 1e-4 for dep in task['deps'])
        assert abs(float(row['MAC']) - task['mac_ops']) < 1.
        assert abs(float(row['physical_read_bytes']) - sum(activity[5:9])) < 1e-5
        assert abs(float(row['physical_write_bytes']) - sum(activity[9:13])) < 1e-5
        arrays[c].append((start, end))
        partitions[c].append((start, end))
        dynamic += task_energy(activity, ratio, c, scenario, static)
        work[q, tid] = (task['op'], task.get('expert'), task['mac_ops'], sum(activity[5:9]), sum(activity[9:13]))
        if 'expert' in task:
            assert int(row['expert']) == task['expert']
            key = q, task['stage'], task['layer'], task['expert']
            assert selections.setdefault(key, c) == c
            source = plan['weight_addresses'].get(task.get('weight_key'))
            if source:
                address = int(row['execution_weight_base'])
                assert address % 8192 == source['base_address'] % 8192
                if source['partition'] != c:
                    matches = [copy for copy in copies if copy['layer'] == task['layer'] and
                               copy['expert'] == task['expert'] and copy['target'] == c and
                               copy['publication_ns'] <= start + 1e-4]
                    assert matches, (q, tid, 'used unpublished expert weights')
        if result['case'] in ('amber_energy', 'contract_energy', 'energy_none'):
            assert ratio == plan['choices'][str(tid)]
    maximum_work_byte_error = 0.
    if reference_work is not None:
        assert set(reference_work) == set(work)
        for key, value in work.items():
            old = reference_work[key]
            assert old[:3] == value[:3]
            error = max(abs(old[3] - value[3]), abs(old[4] - value[4]))
            maximum_work_byte_error = max(maximum_work_byte_error, error)
            # Native floating accumulation can represent 7073792 bytes as
            # 7073791.999999999 at a different OPP. IDs/MAC remain exact.
            assert error < 1e-6, (key, error)
    timing = scenario['timing']
    hop = (timing['noc_link_latency_cycles'] + timing['noc_router_pipeline_cycles']) * timing['noc_cycle_ns']
    actual_dispatch, actual_return = Counter(), Counter()
    for flow in flows:
        src, dst, size = int(flow['src']), int(flow['dst']), int(flow['bytes'])
        path = list(map(int, flow['path'].split('-')))
        assert path[0] == src and path[-1] == dst
        start = float(flow['start_ns'])
        service = int(flow['arbitration_reservation_cycles']) * timing['noc_cycle_ns']
        flits = math.ceil(size / timing['noc_flit_bytes'])
        for index, (a, b) in enumerate(zip(path, path[1:])):
            assert abs(a // 4 - b // 4) + abs(a % 4 - b % 4) == 1
            at = start + index * hop
            links[a, b].append((at, at + service))
            dynamic[a] += flits * p['router_pJ_flit_hop'] * 1e-12
        dynamic[src] += flits * p['ni_pJ_endpoint_flit'] * 1e-12
        dynamic[dst] += flits * p['ni_pJ_endpoint_flit'] * 1e-12
        if flow['kind'] == 'expert_weight_copy':
            dynamic[16 + src] += size / p['sram_access_bytes'] * p['sram_read_pJ_access'] * 1e-12
            dynamic[16 + dst] += size / p['sram_access_bytes'] * p['sram_write_pJ_access'] * 1e-12
        elif flow['kind'] in ('expert_dispatch', 'expert_return'):
            q, tid = int(flow['request']), int(flow['task_id'])
            task = tasks[tid]
            key = q, task['stage'], task['layer'], src, dst, size
            (actual_dispatch if flow['kind'] == 'expert_dispatch' else actual_return)[key] += 1
    semantics = read(PREP / 'semantic_flows.json')['meta_sota']
    expected_dispatch, expected_return = Counter(), Counter()
    for q in range(count):
        for row in semantics:
            key = q, row['phase'], row['layer'], row['expert']
            destination = selections[key]
            home = row['source_cluster']
            if home != destination:
                expected_dispatch[q, row['phase'], row['layer'], home, destination, row['dispatch_bytes']] += 1
                expected_return[q, row['phase'], row['layer'], destination, home, row['combine_bytes']] += 1
    assert actual_dispatch == expected_dispatch, 'expert dispatch identities/bytes changed'
    assert actual_return == expected_return, 'expert return identities/bytes changed'
    for copy in copies:
        src, dst = copy['source'], copy['target']
        start, end = copy['start_ns'], copy['end_ns']
        arrays[src].append((start, end))
        arrays[dst].append((start, end))
        partitions[src].append((start, end))
        partitions[dst].append((start, end))
        item = plan['replica_by_key'][f"{copy['layer']}:{copy['expert']}"]
        payload = sum(int(f['bytes']) for f in flows if f['kind'] == 'expert_weight_copy' and
                      int(f['src']) == src and int(f['dst']) == dst and
                      float(f['start_ns']) >= start - 1e-4 and float(f['end_ns']) <= end + 1e-4)
        assert payload == copy['bytes'] == item['bytes']
        for weight in item['weights']:
            residue = str(weight['source_address'] % 8192)
            chunks = weight['bytes'] // 65536
            for endpoint, suffix, sram in ((src, '_read', 'sram_write_pJ_access'),
                                           (dst, '_write', 'sram_read_pJ_access')):
                record = plan['copy_profiles'][residue + suffix]
                b = bank_indices(endpoint)
                dynamic[b] += chunks * np.maximum(0., np.asarray(record['bank_energy_J']) - static[b] * record['service_ns'] * 1e-9)
                dynamic[endpoint] += weight['bytes'] * 8 * p['hb_pJ_per_bit'] * 1e-12
                dynamic[16 + endpoint] += weight['bytes'] / p['sram_access_bytes'] * p[sram] * 1e-12
    resource_error = max(overlaps(arrays), overlaps(partitions), overlaps(links))
    live = defaultdict(list)
    for entry in buffers:
        live[entry['partition'], entry['slot']].append((entry['allocation_ns'], entry['release_ns']))
        arena = plan['expert_arenas'][str(entry['partition'])]
        assert arena['base_address'] <= entry['base_address']
        assert entry['base_address'] + 2 ** 21 <= arena['end_address']
    overlaps(live)
    with np.load(folder / 'trace.npz') as data:
        power, temperature, initial = data['power_W'], data['temperature_C'], data['initial_state']
        integrated = power.sum(0) * .001
        energy_error = float(np.max(abs(integrated - dynamic - static * result['duration_s'])))
        assert energy_error < 1e-7, energy_error
        assert abs(integrated.sum() - result['energy_J']) < 1e-7
        assert abs(data['components_J'].sum() - integrated.sum()) < 1e-7
        plant = ThermalPlant(45., OP / 'rc')
        plant.state = initial.copy()
        reconstructed = np.asarray([plant.step(row) for row in power])
        thermal_error = float(np.max(abs(temperature - reconstructed)))
        assert thermal_error < 1e-8
        assert abs(float(temperature.max()) - result['peak_C']) < 1e-8
        dose = float((np.maximum(temperature[:, :16] - 60., 0.) *
                      np.maximum(dram_to_logic_regions(temperature[:, 32:]) - 60., 0.)).sum() * .001)
        assert abs(dose - result['D60_K2_s']) < 1e-8
        np.testing.assert_array_equal(initial, warm_state(4))
    return dict(case=result['case'], tasks=len(rows), status='PASS', energy_source_error_J=energy_error,
                full_RC_error_C=thermal_error, resource_overlap_ns=resource_error,
                maximum_native_work_byte_roundoff=maximum_work_byte_error,
                expert_routing='EXACT_FROZEN_IDS_DISPATCH_RETURN_BYTES', copy_publication='PASS',
                trace_sha256=sha(folder / 'trace.npz')), work


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--final', action='store_true')
    args = parser.parse_args()
    plan = read(ROOT / 'plan.json')
    native = read(OP / 'gtp_srs_native_opp_profiles.json')
    scenario = read(OP / 'scenario.json')
    assert sha(OP / 'scenario.json') == native['scenario_sha256']
    tasks = {t['task_id']: t for t in read(PREP / 'gtp_srs_manifest.json')['tasks']}
    capacity = read(PREP / 'gtp_srs_capacity.json')
    ranges = defaultdict(list)
    for c, record in enumerate(capacity):
        ranges[c].append((0, record['total_bytes']))
        arena = plan['expert_arenas'][str(c)]
        ranges[c].append((arena['base_address'], arena['end_address']))
    for item in plan['replicas']:
        for weight in item['weights']:
            ranges[item['target']].append((weight['target_address'], weight['target_address'] + weight['bytes']))
    overlaps(ranges)
    assert all(max(end for _, end in values) <= 2 ** 31 for values in ranges.values())
    results, checks = [], []
    reference = None
    for case in (*REQUIRED, 'dynamic_copy_control'):
        folder = ROOT / f'{case}_4req'
        if (folder / 'summary.json').exists():
            check, work = audit_case(folder, plan, native, tasks, scenario, reference)
            reference = work
            checks.append(check)
            results.append(read(folder / 'summary.json'))
    lookup = {r['case']: r for r in results}
    missing = [case for case in REQUIRED if case not in lookup]
    if 'dynamic' in lookup and lookup['dynamic']['copy_count'] and 'dynamic_copy_control' not in lookup:
        missing.append('dynamic_copy_control')
    if args.final:
        assert not missing, missing
    if 'replica_control' in lookup and 'replica_select' in lookup:
        assert read(ROOT / 'replica_control_4req/copies.json') == read(ROOT / 'replica_select_4req/copies.json')
    audit = dict(status='PASS_COMPLETE' if not missing else 'PARTIAL', pending=missing,
                 total_tasks=sum(c['tasks'] for c in checks), cases=checks, capacity='PASS_WITHIN_ORIGINAL_32GIB',
                 audit_implementation_sha256=sha(__file__))
    (ROOT / 'audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    (ROOT / 'comparison.json').write_text(json.dumps(results, indent=2) + '\n')
    lines = ['# A2.7B：专家动作与路线A验证', '',
        '固定4并发、每请求512 prefill+1 decode；现有建模路由、2GHz、Rconv=3、同一完整暖态、60°C软目标/65°C策略上限/64°C守卫。',
        '每次原生任务派发计10µs控制延迟，符合条件的专家选择另计10µs；复制、端点占用、真实XY传输与热状态连续计入。该延迟为明确模型参数，不是硅片校准。', '',
        '| 方法 | 完整时延 s | 总能量 J | 峰温 °C | D60 K²s | 复制 MiB | 改变位置的专家调用 | ≤65°C |',
        '|---|---:|---:|---:|---:|---:|---:|---|']
    for row in results:
        lines.append(f"| {LABELS[row['case']]} | {row['duration_s']:.6f} | {row['energy_J']:.6f} | {row['peak_C']:.6f} | {row['D60_K2_s']:.6f} | {row['copy_bytes'] / 2**20:.3f} | {row['moved_expert_invocations']} | {row['within_policy_cap']} |")
    pairs = [('amber_energy', 'amber', '能耗选频相对原AMBER'),
             ('contract_energy', 'amber_energy', '同选频下契约准入的独立增量'),
             ('contract_energy', 'amber', '完整路线A相对原AMBER'),
             ('replica_select', 'replica_control', '同预复制下副本选择的独立增量'),
             ('replica_select', 'amber', '含完整预复制的副本方案'),
             ('dynamic', 'amber', '成本感知动态迁移'),
             ('dynamic_forced', 'dynamic_forced_control', '同单次复制的专家迁移干预')]
    lines.append('')
    for candidate, reference, label in pairs:
        if candidate in lookup and reference in lookup:
            a, b = lookup[candidate], lookup[reference]
            lines.append(f"- {label}：时延变化{100 * (a['duration_s'] / b['duration_s'] - 1):+.4f}%，能量变化{100 * (a['energy_J'] / b['energy_J'] - 1):+.4f}%，D60变化{100 * (a['D60_K2_s'] / b['D60_K2_s'] - 1):+.4f}%。")
    if 'contract_energy' in lookup and 'amber_energy' in lookup:
        a, b = lookup['contract_energy'], lookup['amber_energy']
        p = scenario['power']
        curves = read(RUNTIME / 'prepared/memory_curves.json')
        idle = 16 * (p['core_static_W'] + p['lbuf_leak_W'] + p['router_static_W'] +
                     p['ni_static_W'] + p['sram_leak_W'] + curves['1']['idle_W_per_partition'])
        residual = a['energy_J'] - b['energy_J'] - idle * (a['duration_s'] - b['duration_s'])
        lines.append(f"- 同选频准入的能耗归因：固定背景{idle:.9f}W；总能量差扣除背景功耗×时延差后的残差为{residual:.3e}J。")
    if 'dynamic' in lookup and not lookup['dynamic']['copy_count']:
        lines.append('- 成本感知动态策略未触发迁移；不能据此声称实际迁移有效。另列预先固定的单专家付费干预及其同复制对照，检查动作本身。')
    periodic_path = ROOT / 'energy_only_periodic.json'
    if periodic_path.exists():
        periodic = read(periodic_path)
        assert periodic['source_trace_sha256'] == sha(ROOT / 'energy_none_4req/trace.npz')
        lines.append(f"- 仅能耗选频策略没有温度反馈，其固定波形的周期RC诊断峰温为{periodic['periodic_peak_C']:.6f}°C，"
                     f"满足65°C上限：{periodic['within_65C_policy_cap']}。因此单轮64.45°C不能说明持续运行可取消准入。"
                     "该诊断没有把AMBER或契约控制器的轨迹重复冒充其稳态执行。")
    lines.extend(['', '48个候选专家副本按每层前两名prefill MAC与固定容量/邻近/温度规则部署，共792MiB；所有副本的读/传输/写入时间与能量都计费。原专家、Top-k身份和全部有用MAC不变。',
        '增加了独立专家调用工作区及发布/释放规则，均在原32GiB容量内，输入/输出一直保留到combine完成。历史区域交换结果没有混入本次比较。',
        '热契约覆盖当前状态、已承诺任务及在途NoC/复制事件的未来整数1ms RC上界，包含无限尾部。实际任务功耗仍使用原始native profile，不用上界功耗替代执行。',
        '本次是单轮暖态、建模路由、bounded per-task DRAM profile模型验证；不是checkpoint推理、跨轮稳态、硅片实测或独立新颖性证明。',
        f"独立复核：{audit['status']}，共{audit['total_tasks']:,}个任务。待完成：{', '.join(missing) if missing else '无'}。", '',
        '[完整配置](plan.json) · [原始结果](comparison.json) · [独立复核](audit.json) · [基础检查](self_test.json)'])
    (ROOT / 'RESULTS.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps(audit, indent=2))
    print('\n'.join(lines))


if __name__ == '__main__':
    main()

"""Frozen small MoE comparison: replica choice, paid migration and Route A."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np

import run_temperature60_pilot as pilot
from moe60_runtime import ROOT, COPY_PROFILE, SLOT_BYTES, SLOTS, ExpertScheduler, base, banks
from moe60_controller import Controller, KERNEL
from op_thermal import ThermalPlant
from thermal_geometry import dram_to_logic_regions

CASES = ('amber', 'amber_energy', 'contract_full', 'contract_energy', 'energy_none',
         'replica_control', 'replica_select', 'dynamic', 'dynamic_copy_control',
         'dynamic_forced', 'dynamic_forced_control')


def sha(path):
    from portable import sha as portable_sha
    return portable_sha(path)


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def dump(path, value):
    Path(path).write_text(json.dumps(clean(value), indent=2, allow_nan=False) + '\n')


def write_csv(path, rows):
    if not rows:
        return
    keys = list(dict.fromkeys(key for row in rows for key in row))
    with Path(path).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def configuration():
    config = json.loads((pilot.ORIGINAL_PREP / pilot.LOCAL_OP.name / 'amber_config.json').read_text())
    config['online'].update(thermal_target_C=60., thermal_max_C=65., safety_guard_C=1.)
    scenario = json.loads((pilot.LOCAL_OP / 'scenario.json').read_text())
    return scenario, config


def compile_plan():
    from portable import seed_plan
    seed_plan(ROOT)
    target = ROOT / 'plan.json'
    if target.exists():
        plan = json.loads(target.read_text())
        for path, value in plan['source_hashes'].items():
            assert sha(path) == value, path
        return plan
    scenario, config = configuration()
    initial = pilot.warm_state(base, 4)
    controller = Controller(scenario, config, {}, 'amber', initial)
    sim = base.Scheduler('gtp_srs_diagnostic', 4, online_controller=controller,
                         operating_point='2ghz_rconv3')
    choices, table = {}, {}
    group_work = {}
    for tid, task in sim.tasks.items():
        c = sim.memory_partition(task)
        domain = [c, 16 + c, *banks(c)]
        candidates = []
        for ratio in (1., .75, .5):
            profile = sim.profile(task, ratio)
            energy = controller._candidate_energy(sim, task, c, c, ratio)
            candidates.append(dict(OPP=ratio, duration_ns=profile['duration_ns'],
                local_J=float(energy.sum() + controller.static[domain].sum() * profile['duration_ns'] * 1e-9)))
        chosen = min(candidates, key=lambda row: (row['local_J'], row['duration_ns'], -row['OPP']))
        choices[tid] = chosen['OPP']
        table[tid] = dict(op=task['op'], chosen=chosen['OPP'], candidates=candidates)
        if 'expert' in task and task['stage'] == 'prefill':
            key = task['layer'], task['expert']
            group_work[key] = group_work.get(key, 0) + task['mac_ops']
    addresses = json.loads((pilot.ORIGINAL_PREP / 'gtp_srs_addresses.json').read_text())
    capacity = json.loads((pilot.ORIGINAL_PREP / 'gtp_srs_capacity.json').read_text())
    heads, arenas = {}, {}
    for c, record in enumerate(capacity):
        begin = int(math.ceil(record['total_bytes'] / 8192) * 8192)
        end = begin + SLOT_BYTES * SLOTS
        assert end < record['partition_bytes']
        arenas[c] = dict(base_address=begin, end_address=end, slots=SLOTS, slot_bytes=SLOT_BYTES)
        heads[c] = end
    temperature = controller.temperature
    incoming = [0] * 16
    replicas = []
    for layer in range(24):
        selected = sorted((key for key in group_work if key[0] == layer),
                          key=lambda key: (-group_work[key], key[1]))[:2]
        used = set()
        for _, expert in selected:
            source = sim.placement['meta_expert_cluster'][layer][expert]
            options = []
            for dest in range(16):
                if dest == source or dest in used:
                    continue
                if abs(dest // 4 - source // 4) + abs(dest % 4 - source % 4) > 2:
                    continue
                cursor = heads[dest]
                weights = []
                for suffix in ('up', 'gate', 'down'):
                    key = f'l{layer}:e{expert}:{suffix}'
                    entry = addresses[key]
                    assert entry['partition'] == source
                    cursor = int(math.ceil(cursor / 8192) * 8192) + entry['base_address'] % 8192
                    weights.append(dict(key=key, source_address=entry['base_address'],
                                        target_address=cursor, bytes=entry['size_bytes']))
                    cursor += entry['size_bytes']
                if cursor <= capacity[dest]['partition_bytes']:
                    options.append((float(temperature[dest]) + .02 * incoming[dest], dest, cursor, weights))
            assert options
            _, dest, end, weights = min(options)
            heads[dest] = end
            incoming[dest] += 1
            used.add(dest)
            replicas.append(dict(layer=layer, expert=expert, source=source, target=dest,
                                 bytes=sum(w['bytes'] for w in weights), weights=weights))
    copy = json.loads(COPY_PROFILE.read_text())
    for path, value in copy['source_hashes'].items():
        assert sha(path) == value, path
    maximum_home = max(sum(c == partition for c in sim.placement['meta_expert_cluster'][layer])
                       for layer in range(24) for partition in range(16))
    assert 4 * (maximum_home + 1) <= SLOTS
    max_tokens = max(int(math.ceil(t['read_bytes'] / 4096)) for t in sim.tasks.values() if t['op'] == 'expert_pack')
    invocation_bytes = 2 * max_tokens * (2 * 2048 + 3 * 1408) + 8 * 8192
    assert invocation_bytes < 2 ** 21
    sources = [pilot.LOCAL_OP / 'gtp_srs_native_opp_profiles.json', COPY_PROFILE, KERNEL,
               pilot.ORIGINAL_PREP / 'gtp_srs_manifest.json', pilot.ORIGINAL_PREP / 'routing.json',
               pilot.ORIGINAL_PREP / 'gtp_srs_addresses.json', pilot.ORIGINAL_PREP / 'gtp_srs_capacity.json',
               pilot.LOCAL_OP / 'rc/A.csv', pilot.LOCAL_OP / 'rc/B.csv', pilot.LOCAL_OP / 'rc/C.csv']
    plan = dict(status='FROZEN_BEFORE_NEW_MECHANISM_PERFORMANCE_RUNS', replicas=replicas,
        replica_by_key={f"{r['layer']}:{r['expert']}": r for r in replicas}, expert_arenas=arenas,
        final_partition_end=heads, source_scratch_residues=[c['scratch_base_address'] % 8192 for c in capacity],
        weight_addresses={k: v for k, v in addresses.items() if ':e' in k},
        replica_bytes=sum(r['bytes'] for r in replicas), copy_profiles=copy['profiles'],
        choices=choices, task_decision_ns=10000., expert_decision_ns=10000., minimum_gain_ns=10000.,
        preview_wait_ms=256, maximum_experts_per_home_layer=maximum_home,
        maximum_invocation_workspace_bytes=invocation_bytes,
        address_scope='Invocation-private 2MiB expert workspace; original nonexpert/KV arenas preserved. Native aliases require equal modulo-8192 geometry. Bounded-context profiles, no checkpoint numeric or persistent row-state claim.',
        policy_rule='Two highest prefill MAC experts per layer; <=2-hop capacity-feasible copies at distinct destinations ranked by common initial temperature and allocation count. No end-to-end outcomes used.',
        decision_rule='Choose resident replica or pay runtime full expert copy only when bounded causal completion estimate including copy and ingress/egress is better by >10us. Keep original expert identities.',
        costs='10us modeled native admission and 10us eligible expert decision; native 64KiB copy read/XY/write, endpoint reservations, SRAM/HB/DRAM/NoC energy and thermal carry are included. Host timing measured separately, not silicon-calibrated.',
        source_hashes={str(path): sha(path) for path in sources})
    dump(target, plan)
    dump(ROOT / 'energy_OPP_table.json', table)
    print('PLAN_READY', len(replicas), plan['replica_bytes'], 'bytes', flush=True)
    return json.loads(target.read_text())


def runtime_validation(sim):
    check = pilot.validate(sim)
    for key, slot in sim.slots.items():
        assert slot['release_ns'] is not None
        arena = sim.arena[slot['partition']]
        assert arena['base_address'] <= slot['base_address']
        assert slot['base_address'] + 2 ** 21 <= arena['end_address']
    allocations = {}
    for key, slot in sim.slots.items():
        allocations.setdefault((slot['partition'], slot['slot']), []).append((slot['allocation_ns'], slot['release_ns']))
    for periods in allocations.values():
        ordered = sorted(periods)
        assert all(a[1] <= b[0] + 1e-5 for a, b in zip(ordered, ordered[1:]))
    return dict(check, live_expert_workspace='PASS', copied_experts=len(sim.copy_rows),
                expert_invocations=len(sim.locations), preserved_expert_IDs=True)


def code_hashes():
    return {str(path): sha(path) for path in [Path(__file__), pilot.HERE / 'moe60_controller.py',
            pilot.HERE / 'moe60_runtime.py', pilot.HERE / 'graph_scheduler.py', pilot.HERE / 'amber_online_qwen.py',
            ROOT / 'plan.json', ROOT / 'energy_OPP_table.json']}


def run(case, requests):
    plan = compile_plan()
    folder = ROOT / f'{case}_{requests}req'
    folder.mkdir(exist_ok=True)
    target = folder / 'summary.json'
    if target.exists():
        record = json.loads(target.read_text())
        assert record['code_hashes'] == code_hashes()
        print('ALREADY_COMPLETE', target, flush=True)
        return
    for path, value in plan['source_hashes'].items():
        assert sha(path) == value, path
    hashes = code_hashes()
    scenario, config = configuration()
    initial = pilot.warm_state(base, requests)
    choices = {int(k): v for k, v in plan['choices'].items()}
    began = time.monotonic()
    def progress(controller):
        record = dict(case=case, requests=requests, tasks=controller.stage2['decisions'],
                      simulated_s=controller.current_bin * .001, peak_C=float(controller.temperature.max()),
                      host_s=time.monotonic() - began, OPP=dict(controller.stage2),
                      contract_wait_epochs=controller.extra['contract_wait_epochs'])
        dump(folder / 'progress.json', record)
        print('PROGRESS', json.dumps(record), flush=True)
    policy = case if case in ('amber', 'amber_energy', 'contract_full', 'contract_energy', 'energy_none') else 'amber'
    mechanism = case if case in ('replica_control', 'replica_select', 'dynamic', 'dynamic_copy_control',
                                 'dynamic_forced', 'dynamic_forced_control') else 'none'
    control = None
    if case == 'dynamic_copy_control':
        source = ROOT / f'dynamic_{requests}req/copies.json'
        control = json.loads(source.read_text())
    controller = Controller(scenario, config, choices, policy, initial, progress)
    sim = ExpertScheduler(requests, controller, plan, mechanism, control)
    end = sim.run()
    measured_end = math.ceil(end / 1e6) * 1e6
    controller.observe(sim)
    controller.advance(measured_end)
    power, components = base.render_trace(sim, measured_end)
    assert abs(power.sum() * .001 - components.sum()) < 1e-7
    plant = ThermalPlant(45., pilot.LOCAL_OP / 'rc')
    plant.state = initial.copy()
    temperature = np.asarray([plant.step(row) for row in power])
    error = float(np.max(abs(temperature[-1] - controller.temperature)))
    assert error < 1e-5, error
    check = runtime_validation(sim)
    dram = dram_to_logic_regions(temperature[:, 32:])
    dose = float((np.maximum(temperature[:, :16] - 60., 0.) * np.maximum(dram - 60., 0.)).sum() * .001)
    moved = sum(destination != sim.placement['meta_expert_cluster'][key[2]][key[3]]
                for key, destination in sim.locations.items())
    copy_bytes = sum(row['bytes'] for row in sim.copy_rows)
    record = dict(status='COMPLETE_FULL_MOE_GRAPH_DIAGNOSTIC', case=case, requests=requests,
        workload='Qwen1.5-MoE-A2.7B, 512 prefill + 1 decode', routes='Existing frozen modeled routes',
        duration_s=measured_end * 1e-9, throughput_req_s=requests / (measured_end * 1e-9),
        energy_J=float(components.sum()), peak_C=float(temperature.max()), D60_K2_s=dose,
        within_policy_cap=bool(temperature.max() <= 65. + 1e-6), policy_cap_C=65.,
        target_C=60., predictive_guard_C=64., initial_peak_C=float((45. + plant.C @ initial).max()),
        NoC_bytes=sum(flow['bytes'] for flow in sim.net.flows), copy_bytes=copy_bytes,
        expert_invocations=len(sim.locations), moved_expert_invocations=moved,
        copy_count=len(sim.copy_rows), controller=controller.report(), validation=check,
        RC_final_error_C=error, host_seconds=time.monotonic() - began, code_hashes=hashes,
        source_hashes=plan['source_hashes'], task_decision_ns=plan['task_decision_ns'],
        expert_decision_ns=plan['expert_decision_ns'], extra_expert_decision_ns=sim.extra_decision_ns,
        scope='Same native-profile executor, private expert arenas, modeled routes and copied modulo-address geometry. Single warm cohort; not steady state, numerical checkpoint inference or silicon-calibrated controller.')
    write_csv(folder / 'tasks.csv', sim.task_rows)
    write_csv(folder / 'flows.csv', sim.net.flows)
    write_csv(folder / 'stage2.csv', controller.rows)
    dump(folder / 'copies.json', sim.copy_rows)
    dump(folder / 'expert_decisions.json', sim.decisions)
    dump(folder / 'expert_buffers.json', [dict(request=k[0], phase=k[1], layer=k[2], expert=k[3], **v)
                                          for k, v in sim.slots.items()])
    dump(folder / 'geometry_checks.json', sim.geometry_checks)
    np.savez_compressed(folder / 'trace.npz', initial_state=initial, end_state=plant.state,
                        power_W=power, temperature_C=temperature, components_J=components)
    assert code_hashes() == hashes
    dump(target, record)
    print('COMPLETE', json.dumps({k: record[k] for k in ('case', 'requests', 'duration_s', 'energy_J',
          'peak_C', 'D60_K2_s', 'copy_count', 'copy_bytes', 'moved_expert_invocations', 'host_seconds')}), flush=True)


def self_test():
    plan = compile_plan()
    scenario, config = configuration()
    initial = pilot.warm_state(base, 4)
    choices = {int(k): v for k, v in plan['choices'].items()}
    ctl = Controller(scenario, config, choices, 'contract_energy', initial)
    sim = ExpertScheduler(4, ctl, plan)
    tests = []
    for tid in (3, 172, 10530, max(sim.tasks)):
        task = sim.tasks[tid]
        c = sim.cluster(task)
        ratio = choices[tid]
        profile = sim.profile(task, ratio)
        energy = ctl.energy(sim, task, c, c, ratio)
        for offset in (0., 350000., 1500000.):
            end = offset + profile['duration_ns']
            bound = ctl.kernel.idle_bound(ctl.modes) + ctl.kernel.event_bound(offset, end, energy, 0.)
            plant = ThermalPlant(45., pilot.LOCAL_OP / 'rc')
            plant.state = initial.copy()
            maximum_excess = -math.inf
            for index in range(int(math.ceil(end / 1e6)) + 256):
                overlap = max(0., min(end, (index + 1) * 1e6) - max(offset, index * 1e6))
                power = ctl.static + energy * (overlap / profile['duration_ns']) * 1000.
                actual = plant.step(power)
                window = np.searchsorted(ctl.kernel.edges[1:], index + 1, side='left')
                maximum_excess = max(maximum_excess, float((actual - bound[window]).max()))
            assert maximum_excess <= 1e-7, (tid, offset, maximum_excess)
            tests.append(dict(task_id=tid, offset_ns=offset, maximum_bound_excess_K=maximum_excess))
    # Force one real paid copy to exercise publication, endpoint occupancy,
    # staging energy, native read/write and immutable weight-address geometry.
    ctl = Controller(scenario, config, choices, 'amber', initial)
    sim = ExpertScheduler(4, ctl, plan)
    item = plan['replicas'][0]
    sim.copy_expert(item)
    assert sum(row['bytes'] for row in sim.copy_rows) == item['bytes']
    assert sum(flow['bytes'] for flow in sim.net.flows if flow['kind'] == 'expert_weight_copy') == item['bytes']
    power, components = base.render_trace(sim, math.ceil(sim.cursor / 1e6) * 1e6)
    ctl.observe(sim)
    ctl.advance(len(power) * 1e6)
    plant = ThermalPlant(45., pilot.LOCAL_OP / 'rc')
    plant.state = initial.copy()
    temperature = np.asarray([plant.step(row) for row in power])
    assert np.max(abs(temperature[-1] - ctl.temperature)) < 1e-6
    assert abs(power.sum() * .001 - components.sum()) < 1e-8
    ctl.base_ledger()
    now = ctl.current_bin * 1e6
    energy = np.zeros(96)
    energy[0] = 1e-6
    sim.intervals.append((now + 1e5, now + 9e5, energy, np.zeros(7)))
    ctl.observe(sim)
    cached = ctl.base_ledger().copy()
    ctl.ledger = None
    cache_error = float(np.max(abs(cached - ctl.base_ledger())))
    assert cache_error < 1e-9
    producer_ctl = Controller(scenario, config, choices, 'amber', initial)
    producer_sim = ExpertScheduler(4, producer_ctl, plan)
    producer_tid = producer_sim.top4['prefill', 0]
    producer_cluster = producer_sim.tasks[producer_tid]['primary_cluster']
    producer_sim.done[0, producer_tid] = dict(cluster=producer_cluster, end_ns=0.)
    for home in producer_sim.tokens_at_home['prefill', 0]:
        tid = producer_sim.srs_home_norm['prefill', 0, home]
        producer_sim.done[0, tid] = dict(cluster=home, end_ns=0.)
    producer_sim.ensure_scatter(0, 'prefill', 0, (producer_cluster + 1) % 16, 0.)
    assert all(flow['src'] == producer_cluster for flow in producer_sim.net.flows
               if flow['kind'] == 'top4_indices')
    result = dict(status='PASS_NATIVE_COPY_AND_FULL_RC_CONTRACT_TESTS', bounds=tests,
                  forced_copy_bytes=item['bytes'], forced_copy_duration_s=len(power) * .001,
                  forced_copy_peak_C=float(temperature.max()), incremental_ledger_error_K=cache_error,
                  top4_actual_producer_check='PASS', source_hashes=code_hashes())
    dump(ROOT / 'self_test.json', result)
    print(json.dumps(result, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=(*CASES, 'prepare', 'self-test'), required=True)
    parser.add_argument('--requests', choices=(1, 4), type=int, default=4)
    args = parser.parse_args()
    if args.case == 'prepare':
        compile_plan()
    elif args.case == 'self-test':
        self_test()
    else:
        run(args.case, args.requests)


if __name__ == '__main__':
    main()

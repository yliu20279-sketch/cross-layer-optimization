"""Live closed-loop, back-to-back MoE cohorts under a common 65 C cap.

Historical single-cohort inputs/controllers are read-only.  The AMBER forecast
cache below stores only deterministic impulse responses; it does not change
forecast arithmetic, thermal guards, scheduling rules, or modeled latency.
"""
import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
import argparse
import copy
import json
import math
from pathlib import Path
import time

import numpy as np

import run_moe60_mechanisms as old
from moe60_controller import Controller
from moe60_runtime import ExpertScheduler, base
from op_thermal import ThermalPlant
from thermal_geometry import dram_to_logic_regions

from portable import RUNS, reference_case
ROOT = RUNS / 'sustained65'
POLICIES = ('amber_energy', 'contract_energy')


class SustainedController(Controller):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.candidate_cache = {}
        self.response_cache = {}
        self.forecast_calls = 0
        self.forecast_parity_checks = 0
        self.forecast_parity_error = 0.

    def _candidate_key(self, sim, task, compute, partition, ratio):
        return sim.profile_keys[str(task['task_id'])], compute, partition, ratio

    def _candidate_energy(self, sim, task, compute, partition, ratio):
        # Native profiles are immutable, and invocation-private workspaces have
        # the same bank geometry. No policy state enters this energy vector.
        key = self._candidate_key(sim, task, compute, partition, ratio)
        if key not in self.candidate_cache:
            self.candidate_cache[key] = super()._candidate_energy(sim, task, compute, partition, ratio)
        return self.candidate_cache[key]

    def _forecast(self, sim, task, compute, partition, start, ratio):
        # This experiment uses the fixed original expert locations: no remote
        # native operand execution. All actual dispatch/return NoC events still
        # enter observe(), the committed baseline and the independent replay.
        assert compute == partition
        profile = sim.profile(task, ratio)
        duration = float(profile['duration_ns'])
        end = start + duration
        energy = self._candidate_energy(sim, task, compute, partition, ratio)
        base_bin = self.current_bin
        first = max(base_bin, int(start // self.dt_ns))
        latest_committed = max(self.energy_by_bin, default=base_bin)
        last = max(int(math.ceil(end / self.dt_ns)), latest_committed + 1) + int(self.config['lookahead_bins'])
        self._ensure_impulse(last - first)
        state = self._baseline_tail
        for b in range(self._baseline_end, last):
            power = self.static + self.energy_by_bin.get(b, np.zeros(96)) * 1000
            state = self._step_state(state, power)
            self._baseline_rows.append(np.asarray(self.plant.ambient + self.plant.C @ state))
        self._baseline_end, self._baseline_tail = last, state
        key = self._candidate_key(sim, task, compute, partition, ratio)
        response = self.response_cache.setdefault(key, [])
        for index in range(len(response), last - first):
            response.append(self._impulse[index] @ energy)
        delta = np.zeros((last - first, 96))
        begin = max(first, int(start // self.dt_ns))
        finish = min(last, int(math.ceil(end / self.dt_ns)))
        for source in range(begin, finish):
            overlap = max(0., min(end, (source + 1) * self.dt_ns) - max(start, source * self.dt_ns))
            if overlap:
                factor = (overlap / (end - start)) * 1000
                for target_bin in range(source, last):
                    delta[target_bin - first] += response[target_bin - source] * factor
        rows = np.asarray(self._baseline_rows[first - base_bin:last - base_bin]) + delta
        peaks = np.max(rows, axis=1)
        limit = float(self.config['thermal_max_C'] - self.config['safety_guard_C'])
        target = float(self.config['thermal_target_C'])
        result = dict(peak_C=max(float(self.temperature.max()), float(np.max(peaks))),
                      cost=float(np.square(peaks - target).sum()), safe=bool(np.all(peaks <= limit)))
        self.forecast_calls += 1
        if self.forecast_calls <= 128 or self.forecast_calls % 4096 == 0:
            reference = super()._forecast(sim, task, compute, partition, start, ratio)
            error = max(abs(result[k] - reference[k]) for k in ('peak_C', 'cost'))
            self.forecast_parity_error = max(error, self.forecast_parity_error)
            assert error < 1e-10 and result['safe'] == reference['safe'], (result, reference)
            self.forecast_parity_checks += 1
        return result

    def drained_rebase(self):
        # Merely translate the time origin at a drained, integer-ms boundary.
        # Preserve all 1292 states, modal state, last OPP and compiled caches.
        assert not self.energy_by_bin and not self.future_events
        self.current_bin = 0
        self.seen = 0
        self.rows = []
        self.stage1_rows = []
        self.stage1.clear()
        self.stage2.clear()
        self.extra.clear()
        self.bound_evaluations = 0
        self.bound_host_s = 0.
        self.maximum_admitted_bound_C = -math.inf
        self.background = self.ledger = None
        self._invalidate_baseline()


def protocol():
    ROOT.mkdir(exist_ok=True)
    spec = dict(
        status='FROZEN_BEFORE_SUSTAINED_RUNS', workload='Qwen1.5-MoE-A2.7B', requests_per_cohort=4,
        tokens='512 prefill + 1 decode per request; fixed modeled expert routes',
        policies=list(POLICIES), common_soft_target_C=60., common_cap_C=65., common_predictive_guard_C=64.,
        clock_GHz=2., Rconv_K_per_W=3., ambient_C=45.,
        same_opp_table_sha256=old.sha(old.ROOT / 'energy_OPP_table.json'),
        cohort_arrivals='Next four requests released immediately at drained previous-cohort ceil(1ms) boundary; no inter-cohort cool-down.',
        carry='Full 1292-state RC state, modal state, last OPP; no thermal reset. New task and link calendars only after all work drains.',
        task_dispatch_ns=10000., no_migration=True, no_noc_reconfiguration=True,
        convergence=dict(minimum_cohorts=8, maximum_cohorts=24, consecutive_stable_pairs=3, confirmation_cohorts=2,
            full_state_delta_K=.05, block_mean_delta_C=.03, block_peak_delta_C=.03,
            duration_relative_delta=.005, slow_modal_output_drift_C=.01),
        measurement='Final three actual closed-loop cohorts after convergence, including two confirmation cohorts; no repeated temperature-dependent traces.',
        safety='Every actual 1ms RC endpoint in every cohort <=65C, initial state included. Infinite idle tail bounded/replayed separately at final boundary.',
        scope='Bounded per-task native profiles, modeled routes/costs; not checkpoint inference, persistent DRAM command queue, or silicon measurements.',
        sources={**old.code_hashes(), str(Path(__file__).resolve()): old.sha(__file__)})
    path = ROOT / 'protocol.json'
    if path.exists():
        assert json.loads(path.read_text()) == spec
    else:
        old.dump(path, spec)
    return spec


def idle_tail(initial, controller):
    # Exact per-node signed-mode bounds over every future interval, including
    # the infinite tail, plus a directly replayed 120-second idle trace.
    modes = controller.kernel.inverse_transform @ initial
    bound = controller.kernel.idle_bound(modes)
    plant = ThermalPlant(45., old.pilot.LOCAL_OP / 'rc')
    plant.state = initial.copy()
    actual_peak = float((45. + plant.C @ initial).max())
    for _ in range(120000):
        actual_peak = max(actual_peak, float(plant.step(controller.static).max()))
    return dict(infinite_idle_tail_upper_C=float(bound.max()), directly_replayed_idle_peak_C=actual_peak)


def run(policy):
    plan = old.compile_plan()
    spec = protocol()
    folder = ROOT / policy
    folder.mkdir(exist_ok=True)
    if (folder / 'summary.json').exists():
        print('ALREADY_COMPLETE', policy, flush=True)
        return
    assert not list(folder.glob('cohort_*/summary.json')), 'Use complete runner checkpoints; do not silently restart over saved cohorts.'
    scenario, config = old.configuration()
    initial = old.pilot.warm_state(base, 4)
    choices = {int(k): v for k, v in plan['choices'].items()}
    began = time.monotonic()
    active = {'cohort': 0}
    def progress(ctl):
        row = dict(policy=policy, cohort=active['cohort'], tasks=ctl.stage2['decisions'],
                   simulated_cohort_s=ctl.current_bin * .001, temperature_C=float(ctl.temperature.max()),
                   host_seconds=time.monotonic() - began)
        old.dump(folder / 'progress.json', row)
        print('PROGRESS', json.dumps(row), flush=True)
    ctl = SustainedController(scenario, config, choices, policy, initial, progress)
    records = []
    stable = 0
    convergence_at = None
    cumulative_s = 0.
    previous = None
    last_intensity = 0.
    thresholds = spec['convergence']
    for cohort in range(1, thresholds['maximum_cohorts'] + 1):
        active['cohort'] = cohort
        cohort_began = time.monotonic()
        start_state = ctl.plant.state.copy()
        start_modes = ctl.modes.copy()
        opp_history = dict(ctl.last_opp)
        ctl.drained_rebase()
        sim = ExpertScheduler(4, ctl, plan, mechanism='none')
        sim.last_intensity = last_intensity
        end = sim.run()
        last_intensity = sim.last_intensity
        measured_end = math.ceil(end / 1e6) * 1e6
        assert max((f['end_ns'] for f in sim.net.flows), default=0.) <= measured_end + 1e-4
        ctl.observe(sim)
        ctl.advance(measured_end)
        assert not ctl.future_events and not ctl.energy_by_bin
        power, components = base.render_trace(sim, measured_end)
        plant = ThermalPlant(45., old.pilot.LOCAL_OP / 'rc')
        plant.state = start_state.copy()
        temperature = np.asarray([plant.step(row) for row in power])
        state_error = float(np.max(abs(plant.state - ctl.plant.state)))
        assert state_error < 1e-8
        assert abs(power.sum() * .001 - components.sum()) < 1e-7
        assert all(row['opp_ratio'] == choices[row['task_id']] for row in sim.task_rows)
        validation = old.runtime_validation(sim)
        duration = measured_end * 1e-9
        peak = float(max(temperature.max(), (45. + plant.C @ start_state).max()))
        means, peaks = temperature.mean(0), temperature.max(0)
        full_state_delta = float(np.max(abs(plant.state - start_state)))
        slow = int(np.argmax(ctl.kernel.poles))
        slow_drift = float(np.max(abs(ctl.kernel.output[:, slow] * (ctl.modes[slow] - start_modes[slow]))))
        row = dict(cohort=cohort, policy=policy, requests=4, tasks=len(sim.task_rows),
            duration_s=duration, useful_duration_s=end * 1e-9, cumulative_end_s=cumulative_s + duration,
            throughput_req_s=4 / duration, energy_J=float(components.sum()), peak_C=peak,
            within_cap=peak <= 65. + 1e-6, mean_power_W=float(power.sum(1).mean()),
            initial_peak_C=float((45. + plant.C @ start_state).max()),
            end_peak_C=float(temperature[-1].max()), full_state_delta_K=full_state_delta,
            slow_modal_output_drift_C=slow_drift, block_mean_C=means.tolist(), block_peak_C=peaks.tolist(),
            D60_K2_s=float((np.maximum(temperature[:, :16] - 60., 0.) *
                np.maximum(dram_to_logic_regions(temperature[:, 32:]) - 60., 0.)).sum() * .001),
            full_state_replay_error_K=state_error, controller=ctl.report(), validation=validation,
            start_opp_history={str(k): v for k, v in opp_history.items()},
            host_seconds=time.monotonic() - cohort_began, source_hashes=spec['sources'])
        pair_ok = False
        if previous is not None:
            row['block_mean_delta_C'] = float(np.max(abs(means - previous['block_mean_C'])))
            row['block_peak_delta_C'] = float(np.max(abs(peaks - previous['block_peak_C'])))
            row['duration_relative_delta'] = abs(duration / previous['duration_s'] - 1)
            pair_ok = (full_state_delta <= thresholds['full_state_delta_K'] and
                slow_drift <= thresholds['slow_modal_output_drift_C'] and
                row['block_mean_delta_C'] <= thresholds['block_mean_delta_C'] and
                row['block_peak_delta_C'] <= thresholds['block_peak_delta_C'] and
                row['duration_relative_delta'] <= thresholds['duration_relative_delta'])
        stable = stable + 1 if pair_ok else 0
        row['stable_pair'] = pair_ok
        row['consecutive_stable_pairs'] = stable
        if convergence_at is not None and not pair_ok:
            convergence_at = None
        if convergence_at is None and cohort >= thresholds['minimum_cohorts'] and stable >= thresholds['consecutive_stable_pairs']:
            convergence_at = cohort
        row['convergence_candidate_cohort'] = convergence_at
        cf = folder / f'cohort_{cohort:02d}'
        cf.mkdir(exist_ok=True)
        old.write_csv(cf / 'tasks.csv', sim.task_rows)
        old.write_csv(cf / 'flows.csv', sim.net.flows)
        old.write_csv(cf / 'stage2.csv', ctl.rows)
        old.dump(cf / 'expert_buffers.json', [dict(request=k[0], phase=k[1], layer=k[2], expert=k[3], **v)
                  for k, v in sim.slots.items()])
        np.savez_compressed(cf / 'trace.npz', power_W=power, temperature_C=temperature,
                            components_J=components, initial_state=start_state, end_state=plant.state)
        old.dump(cf / 'summary.json', row)
        records.append(row)
        old.dump(folder / 'cohorts.json', records)
        old.dump(folder / 'checkpoint.json', dict(completed_cohorts=cohort, stable_pairs=stable,
            convergence_candidate=convergence_at, cumulative_s=cumulative_s + duration))
        print('COHORT_COMPLETE', json.dumps({k: row.get(k) for k in ('policy', 'cohort', 'duration_s',
            'peak_C', 'full_state_delta_K', 'slow_modal_output_drift_C', 'block_mean_delta_C',
            'block_peak_delta_C', 'duration_relative_delta', 'consecutive_stable_pairs', 'host_seconds')}), flush=True)
        cumulative_s += duration
        previous = row
        for path, digest in spec['sources'].items():
            assert old.sha(path) == digest, path
        if convergence_at is not None and cohort >= convergence_at + thresholds['confirmation_cohorts']:
            break
    converged = convergence_at is not None and len(records) >= convergence_at + thresholds['confirmation_cohorts']
    measurement = records[-3:] if converged else []
    tail = idle_tail(ctl.plant.state, ctl)
    first_old = json.loads((reference_case(policy) / 'summary.json').read_text())
    first_match = all(abs(records[0][k] - first_old[k]) < 1e-9 for k in ('duration_s', 'energy_J', 'peak_C', 'D60_K2_s'))
    assert first_match
    result = dict(status='COMPLETE_CONVERGED' if converged else 'COMPLETE_NOT_CONVERGED', policy=policy,
        completed_cohorts=len(records), total_requests=4 * len(records), total_tasks=sum(r['tasks'] for r in records),
        cumulative_duration_s=cumulative_s, total_energy_J=sum(r['energy_J'] for r in records),
        whole_run_peak_C=max(r['peak_C'] for r in records), all_cohorts_within_65C=all(r['within_cap'] for r in records),
        convergence_cohort=convergence_at, measurement_cohorts=[r['cohort'] for r in measurement],
        measured_mean_cohort_s=(float(np.mean([r['duration_s'] for r in measurement])) if measurement else None),
        measured_throughput_req_s=(12 / sum(r['duration_s'] for r in measurement) if measurement else None),
        measured_energy_per_request_J=(sum(r['energy_J'] for r in measurement) / 12 if measurement else None),
        measured_peak_C=(max(r['peak_C'] for r in measurement) if measurement else None),
        measured_D60_per_cohort_K2_s=(float(np.mean([r['D60_K2_s'] for r in measurement])) if measurement else None),
        forecast_cache_parity_checks=ctl.forecast_parity_checks, forecast_cache_max_error=ctl.forecast_parity_error,
        first_cohort_reproduces_historical_metrics=first_match, host_seconds=time.monotonic() - began,
        no_cooling_gaps=True, native_opp_choices_identical=True, idle_tail=tail,
        protocol_sha256=old.sha(ROOT / 'protocol.json'), sources=spec['sources'])
    old.dump(folder / 'summary.json', result)
    print('POLICY_COMPLETE', json.dumps(result), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--policy', choices=POLICIES, required=True)
    args = parser.parse_args()
    run(args.policy)

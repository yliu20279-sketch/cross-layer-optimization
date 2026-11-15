"""Prospective fixed-window sustained comparison after exploratory cohorts.

Use the full 1292-mode RC model for AMBER forecasts instead of repeatedly
factoring the same physical update. Actual execution and replay still use the
original sparse physical-state RC, with sampled forecast parity checks.
"""
import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
import argparse
import json
import math
from pathlib import Path
import time

import numpy as np

import run_moe65_sustained as original
from moe60_controller import Controller

ROOT = original.ROOT / 'fixed12'
old = original.old


class FastController(original.SustainedController):
    def exact_forecasts(self, sim, trials):
        saved = self._baseline_rows, self._baseline_end, self._baseline_tail
        self._invalidate_baseline()
        try:
            return [Controller._forecast(self, sim, *trial) for trial in trials]
        finally:
            self._baseline_rows, self._baseline_end, self._baseline_tail = saved

    def choose_task(self, sim, ready, default):
        if self.contract_enabled:
            return super().choose_task(sim, ready, default)
        self.observe(sim)
        self.advance(sim.cursor)
        self.stage1['decisions'] += 1
        earliest = self._earliest(sim, default)
        eligible = sorted((key for key in ready if self._earliest(sim, key) <= earliest + self.dt_ns),
                          key=lambda key: (self._earliest(sim, key), key))[:self.config['ready_candidates']]
        scored = []
        for key in eligible:
            task = sim.view(*key)
            c, p = sim.cluster(task), sim.memory_partition(task)
            start = self._earliest(sim, key)
            forecast = self._forecast(sim, task, c, p, start, self.ratio(task))
            scored.append([key, start, forecast, float(self.demand[task['op']]['intensity'])])
        self.stage1['thermal_candidate_evaluations'] += len(scored)
        feasible = [row for row in scored if row[2]['safe']]
        # Identical/symmetric candidate costs can differ in the last few bits
        # between full-order RC representations. Resolve every near tie using
        # the original physical-state arithmetic, including fallback peaks.
        metric = 'cost' if feasible else 'peak_C'
        pool = feasible if feasible else scored
        best = min(row[2][metric] for row in pool)
        tied = [row for row in pool if row[2][metric] <= best + 1e-6]
        if len(tied) > 1:
            trials = [(sim.view(*r[0]), sim.cluster(sim.view(*r[0])),
                       sim.memory_partition(sim.view(*r[0])), r[1], self.ratio(sim.view(*r[0]))) for r in tied]
            exact = self.exact_forecasts(sim, trials)
            for row, value in zip(tied, exact):
                row[2] = value
        feasible = [row for row in scored if row[2]['safe']]
        if feasible:
            chosen = min(feasible, key=lambda row: (row[2]['cost'], row[1],
                abs(row[3] + sim.last_intensity), row[0]))
            self.stage1['feasible'] += 1
        else:
            chosen = min(scored, key=lambda row: (row[2]['peak_C'], row[1], row[0]))
            self.stage1['fallback'] += 1
        self.stage1['reordered'] += chosen[0] != default
        return chosen[0]

    def _forecast(self, sim, task, compute, partition, start, ratio):
        assert compute == partition
        profile = sim.profile(task, ratio)
        end = start + float(profile['duration_ns'])
        energy = self._candidate_energy(sim, task, compute, partition, ratio)
        base_bin = self.current_bin
        first = max(base_bin, int(start // self.dt_ns))
        latest = max(self.energy_by_bin, default=base_bin)
        last = max(int(math.ceil(end / self.dt_ns)), latest + 1) + int(self.config['lookahead_bins'])
        self._ensure_impulse(last - first)
        if not self._baseline_rows:
            self._baseline_modal_tail = self.modes.copy()
        modes = self._baseline_modal_tail
        for b in range(self._baseline_end, last):
            power = self.static + self.energy_by_bin.get(b, np.zeros(96)) * 1000
            modes = self.kernel.poles * modes + self.kernel.U @ power
            self._baseline_rows.append(45. + self.kernel.output @ modes)
        self._baseline_end, self._baseline_modal_tail = last, modes
        response = self.response_cache.setdefault(self._candidate_key(sim, task, compute, partition, ratio), [])
        for index in range(len(response), last - first):
            response.append(self._impulse[index] @ energy)
        delta = np.zeros((last - first, 96))
        begin = max(first, int(start // self.dt_ns))
        finish = min(last, int(math.ceil(end / self.dt_ns)))
        for source in range(begin, finish):
            overlap = max(0., min(end, (source + 1) * self.dt_ns) - max(start, source * self.dt_ns))
            if overlap:
                factor = overlap / (end - start) * 1000
                for target_bin in range(source, last):
                    delta[target_bin - first] += response[target_bin - source] * factor
        peaks = np.max(np.asarray(self._baseline_rows[first - base_bin:last - base_bin]) + delta, axis=1)
        result = dict(peak_C=max(float(self.temperature.max()), float(peaks.max())),
            cost=float(np.square(peaks - self.config['thermal_target_C']).sum()),
            safe=bool(np.all(peaks <= self.config['thermal_max_C'] - self.config['safety_guard_C'])))
        limit = self.config['thermal_max_C'] - self.config['safety_guard_C']
        if np.min(abs(peaks - limit)) < 1e-8:
            result = self.exact_forecasts(sim, [(task, compute, partition, start, ratio)])[0]
        self.forecast_calls += 1
        if self.forecast_calls <= 128 or self.forecast_calls % 4096 == 0:
            saved = self._baseline_rows, self._baseline_end, self._baseline_tail
            self._invalidate_baseline()
            reference = Controller._forecast(self, sim, task, compute, partition, start, ratio)
            self._baseline_rows, self._baseline_end, self._baseline_tail = saved
            error = max(abs(result[k] - reference[k]) for k in ('peak_C', 'cost'))
            self.forecast_parity_error = max(error, self.forecast_parity_error)
            assert error < 1e-7 and result['safe'] == reference['safe'], (result, reference)
            self.forecast_parity_checks += 1
        return result


def protocol():
    old.compile_plan()
    ROOT.mkdir(parents=True, exist_ok=True)
    previous = original.protocol()
    spec = dict(previous)
    spec.update(status='FROZEN_BEFORE_FIXED12_CONFIRMATORY_RUNS', cohorts=12, measurement_cohorts=list(range(7, 13)),
        convergence=dict(block_mean_window_delta_C=.03, duration_window_relative_delta=.01,
            slow_mode_mean_window_delta_C=.03, windows=[[7, 8, 9], [10, 11, 12]]),
        measurement='All twelve actual feedback-controlled cohorts; final six for sustained throughput. Compare cohorts7-9 vs10-12 to check drift. No outcome-based cohort selection.',
        reason='Exploratory controllers show small aperiodic local peak variations; test sustained window stability rather than strict repetition of each full task schedule.',
        acceleration='Full1292-mode baseline propagation only; use original physical RC arithmetic for all near-tied task scores and near-guard forecasts. Actual execution retains original physical sparse RC. Compare original forecast on first128 and every4096 calls; first cohort full native task timing must match historical.',
        sources={**previous['sources'], str(Path(__file__).resolve()): old.sha(__file__)})
    path = ROOT / 'protocol.json'
    if path.exists():
        assert json.loads(path.read_text()) == spec
    else:
        old.dump(path, spec)
    return spec


def run(policy):
    plan = old.compile_plan()
    spec = protocol()
    folder = ROOT / policy
    folder.mkdir(exist_ok=True)
    if (folder / 'summary.json').exists():
        print('ALREADY_COMPLETE', policy, flush=True)
        return
    assert not list(folder.glob('cohort_*/summary.json'))
    scenario, config = old.configuration()
    choices = {int(k): v for k, v in plan['choices'].items()}
    initial = old.pilot.warm_state(original.base, 4)
    active = {'cohort': 0}
    began = time.monotonic()
    def progress(ctl):
        row = dict(policy=policy, cohort=active['cohort'], tasks=ctl.stage2['decisions'],
            simulated_cohort_s=ctl.current_bin * .001, temperature_C=float(ctl.temperature.max()),
            host_seconds=time.monotonic() - began)
        old.dump(folder / 'progress.json', row)
        print('PROGRESS', json.dumps(row), flush=True)
    ctl = FastController(scenario, config, choices, policy, initial, progress)
    records = []
    cumulative = 0.
    last_intensity = 0.
    slow = int(np.argmax(ctl.kernel.poles))
    for cohort in range(1, spec['cohorts'] + 1):
        active['cohort'] = cohort
        cohort_began = time.monotonic()
        start_state, start_modes = ctl.plant.state.copy(), ctl.modes.copy()
        ctl.drained_rebase()
        sim = original.ExpertScheduler(4, ctl, plan, mechanism='none')
        sim.last_intensity = last_intensity
        end = sim.run()
        last_intensity = sim.last_intensity
        measured_end = math.ceil(end / 1e6) * 1e6
        assert max((f['end_ns'] for f in sim.net.flows), default=0.) <= measured_end + 1e-4
        ctl.observe(sim)
        ctl.advance(measured_end)
        assert not ctl.future_events and not ctl.energy_by_bin
        power, components = original.base.render_trace(sim, measured_end)
        plant = original.ThermalPlant(45., old.pilot.LOCAL_OP / 'rc')
        plant.state = start_state.copy()
        temperature = np.asarray([plant.step(row) for row in power])
        assert float(np.max(abs(plant.state - ctl.plant.state))) < 1e-8
        assert abs(power.sum() * .001 - components.sum()) < 1e-7
        assert all(r['opp_ratio'] == choices[r['task_id']] for r in sim.task_rows)
        validation = old.runtime_validation(sim)
        duration = measured_end * 1e-9
        initial_peak = float((45. + plant.C @ start_state).max())
        dose = float((np.maximum(temperature[:, :16] - 60., 0.) *
            np.maximum(original.dram_to_logic_regions(temperature[:, 32:]) - 60., 0.)).sum() * .001)
        row = dict(policy=policy, cohort=cohort, requests=4, tasks=len(sim.task_rows),
            duration_s=duration, cumulative_end_s=cumulative + duration, throughput_req_s=4 / duration,
            energy_J=float(components.sum()), peak_C=max(initial_peak, float(temperature.max())),
            initial_peak_C=initial_peak, end_peak_C=float(temperature[-1].max()),
            block_mean_C=temperature.mean(0).tolist(), block_peak_C=temperature.max(0).tolist(),
            D60_K2_s=dose, full_state_delta_K=float(np.max(abs(plant.state - start_state))),
            slow_modal_output_drift_C=float(np.max(abs(ctl.kernel.output[:, slow] * (ctl.modes[slow] - start_modes[slow])))),
            slow_mode_boundary_C=(ctl.kernel.output[:, slow] * ctl.modes[slow]).tolist(),
            controller=ctl.report(), validation=validation, host_seconds=time.monotonic() - cohort_began,
            source_hashes=spec['sources'])
        row['within_cap'] = row['peak_C'] <= 65. + 1e-6
        assert row['within_cap'], row['peak_C']
        if cohort == 1:
            reference = json.loads((__import__('portable').reference_case(policy) / 'summary.json').read_text())
            assert all(abs(row[k] - reference[k]) < 1e-8 for k in ('duration_s', 'energy_J', 'peak_C', 'D60_K2_s'))
        cf = folder / f'cohort_{cohort:02d}'
        cf.mkdir(exist_ok=True)
        old.write_csv(cf / 'tasks.csv', sim.task_rows)
        old.write_csv(cf / 'flows.csv', sim.net.flows)
        old.write_csv(cf / 'stage2.csv', ctl.rows)
        old.dump(cf / 'expert_buffers.json', [dict(request=k[0], phase=k[1], layer=k[2], expert=k[3], **v)
            for k, v in sim.slots.items()])
        np.savez_compressed(cf / 'trace.npz', power_W=power, components_J=components,
            temperature_C=temperature, initial_state=start_state, end_state=plant.state)
        old.dump(cf / 'summary.json', row)
        if cohort == 1:
            __import__('portable').assert_first_schedule(cf, policy)
        records.append(row)
        old.dump(folder / 'cohorts.json', records)
        cumulative += duration
        print('COHORT_COMPLETE', json.dumps({k: row[k] for k in ['policy', 'cohort', 'duration_s',
            'peak_C', 'full_state_delta_K', 'slow_modal_output_drift_C', 'host_seconds']}), flush=True)
        for path, digest in spec['sources'].items():
            assert old.sha(path) == digest, path
    measurement = records[6:12]
    first, second = records[6:9], records[9:12]
    weighted = lambda group: np.average(np.array([r['block_mean_C'] for r in group]), axis=0,
                                         weights=[r['duration_s'] for r in group])
    window = dict(block_mean_delta_C=float(np.max(abs(weighted(second) - weighted(first)))),
        duration_relative_delta=abs(sum(r['duration_s'] for r in second) / sum(r['duration_s'] for r in first) - 1),
        slow_mode_mean_delta_C=float(np.max(abs(np.mean([r['slow_mode_boundary_C'] for r in second], axis=0) -
                                                np.mean([r['slow_mode_boundary_C'] for r in first], axis=0)))))
    window['stable'] = (window['block_mean_delta_C'] <= spec['convergence']['block_mean_window_delta_C'] and
        window['duration_relative_delta'] <= spec['convergence']['duration_window_relative_delta'] and
        window['slow_mode_mean_delta_C'] <= spec['convergence']['slow_mode_mean_window_delta_C'])
    result = dict(status='COMPLETE_FIXED12', policy=policy, completed_cohorts=12, total_requests=48,
        total_tasks=sum(r['tasks'] for r in records), cumulative_duration_s=cumulative,
        total_energy_J=sum(r['energy_J'] for r in records), all_cohorts_within_65C=all(r['within_cap'] for r in records),
        whole_run_peak_C=max(r['peak_C'] for r in records), measurement_cohorts=list(range(7, 13)),
        measured_mean_cohort_s=float(np.mean([r['duration_s'] for r in measurement])),
        measured_throughput_req_s=24 / sum(r['duration_s'] for r in measurement),
        measured_energy_per_request_J=sum(r['energy_J'] for r in measurement) / 24,
        measured_peak_C=max(r['peak_C'] for r in measurement),
        measured_D60_per_cohort_K2_s=float(np.mean([r['D60_K2_s'] for r in measurement])),
        stability=window, forecast_parity_checks=ctl.forecast_parity_checks,
        forecast_max_parity_error=ctl.forecast_parity_error, host_seconds=time.monotonic() - began,
        idle_tail=original.idle_tail(ctl.plant.state, ctl),
        no_cooling_gaps=True, native_opp_choices_identical=True,
        protocol_sha256=old.sha(ROOT / 'protocol.json'), sources=spec['sources'])
    old.dump(folder / 'summary.json', result)
    print('POLICY_COMPLETE', json.dumps(result), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--policy', choices=original.POLICIES)
    parser.add_argument('--plan', action='store_true')
    args = parser.parse_args()
    if args.plan:
        protocol()
    else:
        assert args.policy
        run(args.policy)

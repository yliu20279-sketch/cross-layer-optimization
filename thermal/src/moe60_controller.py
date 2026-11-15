"""MoE pilot controllers on the unchanged task/NoC/1292-state RC executor."""
import functools
import math
import time
from collections import Counter
from pathlib import Path

import numpy as np

from amber_online_qwen import QwenAmberOnline

from portable import kernel_path
KERNEL = kernel_path()


class EnvelopeKernel:
    def __init__(self, path=KERNEL):
        with np.load(path) as data:
            for name in ('poles', 'U', 'output', 'inverse_transform', 'idle_power',
                         'idle_modes', 'idle_temperature', 'edges', 'impulse_upper_K_per_J'):
                setattr(self, name, data[name].copy())
        self.logp = np.log(self.poles)
        self.left = self.power(self.edges[:-1]).T
        self.right = self.power(self.edges[1:]).T

    def power(self, times):
        times = np.asarray(times)
        result = np.zeros((len(times), len(self.poles)))
        finite = np.isfinite(times)
        result[finite] = np.exp(times[finite, None] * self.logp)
        return result

    def idle_bound(self, modes):
        terms = self.output * (modes - self.idle_modes)[None, :]
        return (self.idle_temperature[:, None] +
                np.maximum(terms, 0.) @ self.left +
                np.minimum(terms, 0.) @ self.right).T + 1e-8

    @functools.lru_cache(maxsize=8192)
    def rectangle(self, indices, values, duration):
        """Interval upper bound for a nonnegative constant-power rectangle."""
        q = self.U[:, indices] @ np.asarray(values) / (1. - self.poles)
        pulse = q * (-np.expm1(duration * self.logp))
        terms = self.output * pulse[None, :]
        left = np.maximum(0., self.edges[:-1] - duration)
        right = np.maximum(0., self.edges[1:] - duration)
        upper = (np.maximum(terms, 0.) @ self.power(left).T +
                 np.minimum(terms, 0.) @ self.power(right).T).T
        during = self.edges[1:] <= duration
        if during.any():
            steps = q[:, None] * (-np.expm1(np.outer(self.logp, self.edges[1:][during])))
            upper[during] = (self.output @ steps).T
        crossing = (self.edges[:-1] < duration) & (self.edges[1:] > duration)
        upper[crossing] = np.maximum(upper[crossing], self.output @ pulse)
        result = np.maximum(upper, 0.) + 1e-8
        result.flags.writeable = False
        return result

    def event_bound(self, start, end, energy, now):
        remaining = max(0., end - max(now, start)) / (end - start)
        impulse = self.impulse_upper_K_per_J @ (energy * remaining)
        if start >= now + 1e6 or end - max(now, start) <= 1e6:
            return impulse[None, :]
        power = energy / ((end - start) * 1e-9)
        indices = tuple(np.flatnonzero(power).tolist())
        values = tuple(power[list(indices)].tolist())
        duration = int(math.ceil((end - now) / 1e6))
        rectangle = self.rectangle(indices, values, duration)
        return np.minimum(rectangle, impulse[None, :] + 1e-8)


class Controller(QwenAmberOnline):
    def __init__(self, scenario, config, choices, policy, initial, progress=None):
        super().__init__(scenario, list(range(16)), config, '2ghz_rconv3')
        self.policy = policy
        self.choices = choices
        self.energy_selection = policy in ('amber_energy', 'contract_energy', 'energy_none')
        self.contract_enabled = policy.startswith('contract_')
        self.unprotected = policy == 'energy_none'
        self.plant.state = initial.copy()
        self.temperature = self.plant.ambient + self.plant.C @ initial
        self._invalidate_baseline()
        self.kernel = EnvelopeKernel()
        assert np.max(abs(self.static - self.kernel.idle_power)) < 1e-12
        self.modes = self.kernel.inverse_transform @ initial
        self.future_events = []
        self.background = None
        self.ledger = None
        self.extra = Counter()
        self.progress = progress
        self.maximum_admitted_bound_C = -math.inf
        self.bound_evaluations = 0
        self.bound_host_s = 0.
        self.energy_cache = {}

    def ratio(self, task):
        return self.choices[task['task_id']] if self.energy_selection else 1.

    def observe(self, sim):
        old = self.seen
        new = sim.intervals[old:]
        self.future_events.extend(new)
        super().observe(sim)
        if old != self.seen:
            # The thermal state/bin is unchanged during observe. Preserve
            # exactly the same sum and add only newly committed events.
            if self.ledger is not None:
                value = self.ledger.copy()
                now = self.current_bin * self.dt_ns
                for start, end, energy, _ in new:
                    if end > now:
                        value += self.kernel.event_bound(start, end, energy, now)
                self.ledger = value

    def advance(self, ns):
        while (self.current_bin + 1) * self.dt_ns <= ns + 1e-7:
            power = self.static + self.energy_by_bin.pop(self.current_bin, np.zeros(96)) * 1000.
            self.temperature = self.plant.step(power)
            self.modes = self.kernel.poles * self.modes + self.kernel.U @ power
            self.current_bin += 1
            self._invalidate_baseline()
            self.background = self.ledger = None
        now = self.current_bin * self.dt_ns
        self.future_events = [event for event in self.future_events if event[1] > now]

    def energy(self, sim, task, cluster, partition, ratio):
        key = (sim.profile_keys[str(task['task_id'])], cluster, partition, ratio)
        if key not in self.energy_cache:
            self.energy_cache[key] = self._candidate_energy(sim, task, cluster, partition, ratio)
        return self.energy_cache[key]

    def base_ledger(self):
        if self.ledger is None:
            if self.background is None:
                self.background = self.kernel.idle_bound(self.modes)
            value = self.background.copy()
            now = self.current_bin * self.dt_ns
            for start, end, energy, _ in self.future_events:
                if end > now:
                    value += self.kernel.event_bound(start, end, energy, now)
            self.ledger = value
        return self.ledger

    def certified(self, sim, start, end, energy):
        self.observe(sim)
        self.advance(sim.cursor)
        began = time.monotonic()
        now = self.current_bin * self.dt_ns
        bound = self.base_ledger() + self.kernel.event_bound(start, end, energy, now)
        peak = float(bound.max())
        self.bound_evaluations += 1
        self.bound_host_s += time.monotonic() - began
        return peak <= self.config['thermal_max_C'] - self.config['safety_guard_C'] - 1e-6, peak

    def wait_epoch(self, sim):
        sim.cursor = max(sim.cursor, (self.current_bin + 1) * self.dt_ns)
        self.advance(sim.cursor)
        self.extra['contract_wait_epochs'] += 1
        if self.extra['contract_wait_epochs'] > 250000:
            raise RuntimeError('Contract controller exceeded the fixed 250-second wait budget')

    def _earliest(self, sim, key):
        task = sim.view(*key)
        return max([sim.done[key[0], dep]['end_ns'] for dep in task['deps']] +
                   [sim.array_free[sim.cluster(task)], sim.partition_free[sim.memory_partition(task)], sim.cursor])

    def choose_task(self, sim, ready, default):
        self.observe(sim)
        self.advance(sim.cursor)
        self.stage1['decisions'] += 1
        if self.unprotected:
            return default
        earliest = self._earliest(sim, default)
        eligible = sorted((key for key in ready if self._earliest(sim, key) <= earliest + self.dt_ns),
                          key=lambda key: (self._earliest(sim, key), key))[:self.config['ready_candidates']]
        scored = []
        for key in eligible:
            task = sim.view(*key)
            c, p = sim.cluster(task), sim.memory_partition(task)
            start = self._earliest(sim, key)
            ratio = self.ratio(task)
            if self.contract_enabled:
                profile = sim.profile(task, ratio)
                safe, peak = self.certified(sim, start, start + profile['duration_ns'],
                                            self.energy(sim, task, c, p, ratio))
                forecast = dict(safe=safe, peak_C=peak, cost=start)
            else:
                forecast = self._forecast(sim, task, c, p, start, ratio)
            scored.append((key, start, forecast, float(self.demand[task['op']]['intensity'])))
        self.stage1['thermal_candidate_evaluations'] += len(scored)
        feasible = [row for row in scored if row[2]['safe']]
        if feasible:
            chosen = min(feasible, key=lambda row: (row[2]['cost'], row[1],
                         abs(row[3] + sim.last_intensity), row[0]))
            self.stage1['feasible'] += 1
        elif self.contract_enabled:
            self.wait_epoch(sim)
            return None
        else:
            chosen = min(scored, key=lambda row: (row[2]['peak_C'], row[1], row[0]))
            self.stage1['fallback'] += 1
        self.stage1['reordered'] += chosen[0] != default
        return chosen[0]

    def choose_opp(self, sim, task, compute, partition, ready, request=None):
        if not (self.energy_selection or self.contract_enabled or self.unprotected):
            result = super().choose_opp(sim, task, compute, partition, ready, request)
            self.notify()
            return result
        self.observe(sim)
        self.advance(sim.cursor)
        start = max(ready, sim.array_free[compute], sim.partition_free[partition], sim.cursor)
        ratio = self.ratio(task)
        self.stage2['decisions'] += 1
        first = start
        while True:
            profile = sim.profile(task, ratio)
            if self.unprotected:
                safe, peak = True, float(self.temperature.max())
            elif self.contract_enabled:
                safe, peak = self.certified(sim, start, start + profile['duration_ns'],
                                            self.energy(sim, task, compute, partition, ratio))
            else:
                forecast = self._forecast(sim, task, compute, partition, start, ratio)
                safe, peak = forecast['safe'], forecast['peak_C']
                self.stage2['thermal_forecasts'] += 1
            if safe:
                break
            if self.contract_enabled:
                self.wait_epoch(sim)
                start = max(start, sim.cursor)
            else:
                start += self.dt_ns
                if start - first > self.config['max_defer_bins'] * self.dt_ns:
                    raise RuntimeError('No safe selected OPP in the frozen deferral window')
        self.stage2[f'opp_{ratio:g}'] += 1
        self.stage2['deferred_1ms_bins'] += int(math.ceil((start - first) / self.dt_ns))
        previous = self.last_opp[compute]
        self.stage2['opp_switches'] += previous != ratio
        self.last_opp[compute] = ratio
        if self.contract_enabled:
            self.maximum_admitted_bound_C = max(self.maximum_admitted_bound_C, peak)
        self.rows.append(dict(request=request, task_id=task['task_id'], cluster=compute,
                              chosen_opp=ratio, scheduled_start_ns=start, predicted_peak_C=peak,
                              deferred_bins=int(math.ceil((start - first) / self.dt_ns))))
        self.notify()
        return ratio, self.voltages[ratio], start

    def notify(self):
        if self.progress and self.stage2['decisions'] % 2000 == 0:
            self.progress(self)

    def gate_event(self, sim, start, end, energy, force=False):
        if not (self.contract_enabled or force):
            return start
        while not self.certified(sim, start, end, energy)[0]:
            duration = end - start
            self.wait_epoch(sim)
            start = max(start, sim.cursor)
            end = start + duration
        return start

    def report(self):
        return dict(super().report(), extra=dict(self.extra),
                    compiled_bound_checks=self.bound_evaluations,
                    compiled_bound_host_seconds=self.bound_host_s,
                    maximum_admitted_bound_C=(self.maximum_admitted_bound_C if
                                              math.isfinite(self.maximum_admitted_bound_C) else None),
                    contract_scope='All future integer 1ms RC endpoints; constant native task power and every committed NoC/copy event. Exact model, RR1. No silicon cost calibration.')

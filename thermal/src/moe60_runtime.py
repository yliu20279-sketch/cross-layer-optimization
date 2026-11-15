"""Expert-instance placement and fully charged expert-weight copies.

All numerical execution remains the existing bounded native-profile model.
Experts keep their identity and routes. Only their physical resident copy and
execution buffers change, with address-signature and live-capacity checks.
"""
import copy
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

import run_temperature60_pilot as pilot
base, _ = pilot.prepare()
from graph_scheduler import thermal_bank
from sota_compare import Network
from moe60_controller import Controller

from portable import RUNS, INPUT
ROOT = RUNS / 'mechanisms'
CHUNK = 65536
SLOT_BYTES = 2 ** 21 + 8192
SLOTS = 32
COPY_PROFILE = INPUT / 'copy_profile.json'


def banks(partition):
    return [32 + thermal_bank(partition, bank) for bank in range(4)]


def flow_energy(scenario, flow, staging=False):
    p = scenario['power']
    energy = np.zeros(96)
    component = np.zeros(7)
    flits = math.ceil(flow['bytes'] / scenario['timing']['noc_flit_bytes'])
    path = list(map(int, flow['path'].split('-')))
    for node in path[:-1]:
        energy[node] += flits * p['router_pJ_flit_hop'] * 1e-12
    for node in (flow['src'], flow['dst']):
        energy[node] += flits * p['ni_pJ_endpoint_flit'] * 1e-12
    component[3] = flits * flow['hops'] * p['router_pJ_flit_hop'] * 1e-12
    component[4] = 2 * flits * p['ni_pJ_endpoint_flit'] * 1e-12
    if staging:
        access = flow['bytes'] / p['sram_access_bytes']
        energy[16 + flow['src']] += access * p['sram_read_pJ_access'] * 1e-12
        energy[16 + flow['dst']] += access * p['sram_write_pJ_access'] * 1e-12
        component[1] += access * (p['sram_read_pJ_access'] + p['sram_write_pJ_access']) * 1e-12
    assert abs(energy.sum() - component.sum()) < 1e-10
    return energy, component


class ExpertScheduler(base.Scheduler):
    def __init__(self, requests, controller, plan, mechanism='none', copy_control=None):
        super().__init__('gtp_srs_diagnostic', requests, list(range(16)), controller,
                         operating_point='2ghz_rconv3')
        self.plan = plan
        self.mechanism = mechanism
        self.locations = {}
        self.resident = set()
        self.copy_rows = []
        self.decisions = []
        self.geometry_checks = []
        self.arena = {int(key): value for key, value in plan['expert_arenas'].items()}
        self.slot_free = {c: np.zeros(SLOTS) for c in range(16)}
        self.slots = {}
        self.groups = defaultdict(list)
        self.top4 = {}
        for task in self.tasks.values():
            if 'expert' in task:
                self.groups[task['stage'], task['layer'], task['expert']].append(task['task_id'])
            if task['op'] == 'top4':
                self.top4[task['stage'], task['layer']] = task['task_id']
        self.copy_control = {(int(row['request']), row['phase'], int(row['layer']), int(row['expert'])): row
                             for row in (copy_control or [])}
        self.triggered_controls = set()
        self.extra_decision_ns = 0.

    def home(self, task):
        return self.placement['meta_expert_cluster'][task['layer']][task['expert']]

    def invocation(self, request, task):
        return request, task['stage'], task['layer'], task['expert']

    def view(self, request, tid):
        task = self.tasks[tid]
        if 'expert' not in task:
            return task
        key = self.invocation(request, task)
        result = dict(task)
        result['execution_partition'] = self.locations.get(key, self.home(task))
        result['_request'] = request
        if key in self.slots:
            result['execution_workspace_base'] = self.slots[key]['base_address']
        return result

    def memory_partition(self, task):
        return task.get('execution_partition', super().memory_partition(task))

    def cluster(self, task):
        return self.memory_partition(task)

    def profile(self, task, ratio=1.):
        if '_preview_profiles' in task:
            return task['_preview_profiles'][ratio]
        return super().profile(task, ratio)

    def earliest(self, key):
        task = self.view(*key)
        return max([self.done[key[0], dep]['end_ns'] for dep in task['deps']] +
                   [self.array_free[self.cluster(task)], self.partition_free[self.memory_partition(task)], self.cursor])

    def ensure_scatter(self, request, phase, layer, owner, ready):
        producer = self.done[request, self.top4[phase, layer]]
        return super().ensure_scatter(request, phase, layer, producer['cluster'],
                                      max(ready, producer['end_ns']))

    def send(self, src, dst, size, ready, kind, key, staging=False):
        if src == dst or size <= 0:
            return ready
        force = kind == 'expert_weight_copy'
        while True:
            preview = Network(self.sc)
            preview.links = self.net.links.copy()
            preview.transfer(src, dst, size, max(ready, self.cursor), kind, key, 'full_global')
            flow = preview.flows[-1]
            energy, _ = flow_energy(self.sc, flow, staging)
            gated = self.online.gate_event(self, flow['start_ns'], flow['end_ns'], energy, force=force)
            if gated <= flow['start_ns'] + 1e-7:
                break
            ready = max(ready, gated)
        first = len(self.net.flows)
        end = self.net.transfer(src, dst, size, max(ready, self.cursor), kind, key, 'full_global')
        self.flow_energy(first)
        if staging:
            flow = self.net.flows[-1]
            full, full_components = flow_energy(self.sc, flow, True)
            plain, plain_components = flow_energy(self.sc, flow, False)
            self.intervals.append((flow['start_ns'], flow['end_ns'], full - plain,
                                   full_components - plain_components))
        return end

    def copy_leg(self, partition, start, record, write):
        duration = record['service_ns']
        energy = np.zeros(96)
        component = np.zeros(7)
        p = self.sc['power']
        energy[partition] = CHUNK * 8 * p['hb_pJ_per_bit'] * 1e-12
        sram_pj = p['sram_read_pJ_access'] if write else p['sram_write_pJ_access']
        energy[16 + partition] = CHUNK / p['sram_access_bytes'] * sram_pj * 1e-12
        dynamic = np.maximum(0., np.asarray(record['bank_energy_J']) -
                             self.online.static[banks(partition)] * duration * 1e-9)
        energy[banks(partition)] = dynamic
        component[1] = energy[16 + partition]
        component[5] = energy[partition]
        component[6] = dynamic.sum()
        start = self.online.gate_event(self, start, start + duration, energy, force=True)
        self.intervals.append((start, start + duration, energy, component))
        return start + duration

    def copy_expert(self, item, request=-1, phase='setup'):
        src, dst = item['source'], item['target']
        began = max(self.cursor, self.array_free[src], self.array_free[dst],
                    self.partition_free[src], self.partition_free[dst])
        now = began
        for weight in item['weights']:
            residue = str(weight['source_address'] % 8192)
            assert weight['bytes'] % CHUNK == 0
            assert weight['target_address'] % 8192 == int(residue)
            rd = self.plan['copy_profiles'][residue + '_read']
            wr = self.plan['copy_profiles'][residue + '_write']
            for offset in range(0, weight['bytes'], CHUNK):
                now = max(now, self.cursor)
                now = self.copy_leg(src, now, rd, False)
                self.array_free[[src, dst]] = now
                self.partition_free[[src, dst]] = now
                now = self.send(src, dst, CHUNK, now, 'expert_weight_copy',
                                (request, -100), staging=True)
                now = self.copy_leg(dst, now, wr, True)
                self.array_free[[src, dst]] = now
                self.partition_free[[src, dst]] = now
        self.cursor = max(self.cursor, now)
        self.online.observe(self)
        self.online.advance(self.cursor)
        self.resident.add((item['layer'], item['expert']))
        self.copy_rows.append(dict(request=request, phase=phase, layer=item['layer'], expert=item['expert'],
                                   source=src, target=dst, bytes=item['bytes'], start_ns=began, end_ns=now,
                                   publication_ns=now))
        return now

    def prelude(self):
        if self.mechanism in ('replica_control', 'replica_select'):
            for item in self.plan['replicas']:
                self.copy_expert(item)

    def allocate(self, request, task, partition):
        key = self.invocation(request, task)
        if key in self.slots:
            return
        available = np.flatnonzero(self.slot_free[partition] <= self.cursor + 1e-5)
        if not len(available):
            raise RuntimeError('Expert live-output arena exhausted; no uncharged storage fallback')
        slot = int(available[0])
        source = self.home(task)
        residue = self.plan['source_scratch_residues'][source]
        base_address = self.arena[partition]['base_address'] + slot * SLOT_BYTES + residue
        assert base_address % 8192 == residue
        self.slot_free[partition][slot] = math.inf
        self.slots[key] = dict(partition=partition, slot=slot, base_address=base_address,
                               allocation_ns=self.cursor, release_ns=None)
        self.geometry_checks.append(dict(request=request, phase=task['stage'], layer=task['layer'],
            expert=task['expert'], source=source, partition=partition, workspace_base=base_address,
            source_workspace_residue=residue, slot_bytes=SLOT_BYTES))

    def preview_group(self, request, task, destination, copy_item=None):
        """Bounded causal score; no future trace or full-DAG branch replay."""
        c = destination
        network = Network(self.sc)
        network.links = self.net.links.copy()
        ready = max([self.done[request, dep]['end_ns'] for dep in task['deps']] + [self.cursor])
        ready = max(ready, self.array_free[c], self.partition_free[c])
        copy_energy = np.zeros(96)
        if copy_item is not None:
            source = copy_item['source']
            ready = max(ready, self.array_free[source], self.partition_free[source])
            p = self.sc['power']
            for weight in copy_item['weights']:
                residue = str(weight['source_address'] % 8192)
                rd, wr = (self.plan['copy_profiles'][residue + suffix] for suffix in ('_read', '_write'))
                chunks = weight['bytes'] // CHUNK
                # Explicit serialized read/XY/write service on the real current link calendar.
                for _ in range(chunks):
                    ready += rd['service_ns']
                    ready = network.transfer(source, c, CHUNK, ready, 'expert_weight_copy', (-1, -1))
                    ready += wr['service_ns']
                for endpoint, record in ((source, rd), (c, wr)):
                    copy_energy[banks(endpoint)] += chunks * np.maximum(
                        0., np.asarray(record['bank_energy_J']) - self.online.static[banks(endpoint)] * record['service_ns'] * 1e-9)
                    copy_energy[endpoint] += weight['bytes'] * 8 * p['hb_pJ_per_bit'] * 1e-12
                    copy_energy[16 + endpoint] += weight['bytes'] / p['sram_access_bytes'] * (
                        p['sram_read_pJ_access'] + p['sram_write_pJ_access']) * 1e-12
            for flow in network.flows:
                copy_energy += flow_energy(self.sc, flow)[0]
        times = self.scatter_ready.get((request, task['stage'], task['layer']))
        if times is None:
            producer = self.done[request, self.top4[task['stage'], task['layer']]]
            times = {}
            for home, count in self.tokens_at_home[task['stage'], task['layer']].items():
                source = self.done[request, self.srs_home_norm[task['stage'], task['layer'], home]]
                at = max(self.cursor, source['end_ns'], producer['end_ns'], ready)
                times[home] = network.transfer(producer['cluster'], home, 16 * count,
                                               at, 'top4_indices', (-1, -1))
        flows = self.flow_index[task['stage'], task['layer'], task['expert']]
        for flow in flows:
            ready = max(ready, network.transfer(flow['source_cluster'], c, flow['dispatch_bytes'],
                                                max(ready, times[flow['source_cluster']]), 'expert_dispatch', (-1, -1)))
        ids = self.groups[task['stage'], task['layer'], task['expert']]
        pseudo = dict(task)
        pseudo['_preview_profiles'] = {}
        for ratio in (1., .75, .5):
            records = [self.profile(self.tasks[tid], ratio) for tid in ids]
            pseudo['_preview_profiles'][ratio] = dict(duration_ns=sum(r['duration_ns'] for r in records),
                                                      activity=np.sum([r['activity'] for r in records], axis=0))
        extra = self.online.kernel.impulse_upper_K_per_J @ copy_energy
        self.online.observe(self)
        self.online.advance(self.cursor)
        for wait in range(self.plan['preview_wait_ms'] + 1):
            start = ready + wait * 1e6
            for ratio in (1., .75, .5):
                forecast = self.online._forecast(self, pseudo, c, c, start, ratio)
                if forecast['safe'] and forecast['peak_C'] + float(extra.max()) <= 64.:
                    end = start + pseudo['_preview_profiles'][ratio]['duration_ns']
                    for flow in flows:
                        end = max(end, network.transfer(c, flow['source_cluster'], flow['combine_bytes'],
                                                       end, 'expert_return', (-1, -1)))
                    return dict(finish_ns=end, waiting_ms=wait, OPP=ratio,
                                forecast_peak_C=forecast['peak_C'], copy_upper_K=float(extra.max()))
        return dict(finish_ns=math.inf, waiting_ms=None, OPP=None,
                    forecast_peak_C=None, copy_upper_K=float(extra.max()))

    def resolve(self, request, task):
        key = self.invocation(request, task)
        if key in self.locations:
            return
        home = self.home(task)
        target = home
        item = self.plan['replica_by_key'].get(f"{task['layer']}:{task['expert']}")
        if item and self.mechanism in ('replica_control', 'replica_select', 'dynamic', 'dynamic_copy_control',
                                        'dynamic_forced', 'dynamic_forced_control'):
            self.cursor += self.plan['expert_decision_ns']
            self.extra_decision_ns += self.plan['expert_decision_ns']
            forced = self.plan['replicas'][0]
            forced_key = (0, 'prefill', forced['layer'], forced['expert'])
            if self.mechanism in ('dynamic_forced', 'dynamic_forced_control') and key == forced_key:
                self.copy_expert(item, request, task['stage'])
                if self.mechanism == 'dynamic_forced':
                    target = item['target']
            elif self.mechanism == 'dynamic_copy_control' and key in self.copy_control:
                self.copy_expert(item, request, task['stage'])
                self.triggered_controls.add(key)
            elif self.mechanism in ('replica_select', 'dynamic'):
                original = self.preview_group(request, task, home)
                needs_copy = (task['layer'], task['expert']) not in self.resident
                trial = self.preview_group(request, task, item['target'], item if needs_copy else None)
                accepted = trial['finish_ns'] + self.plan['minimum_gain_ns'] < original['finish_ns']
                self.decisions.append(dict(request=request, phase=task['stage'], layer=task['layer'],
                    expert=task['expert'], home=home, target=item['target'], needs_copy=needs_copy,
                    accepted=accepted, original=original, alternative=trial))
                if accepted:
                    if needs_copy:
                        self.copy_expert(item, request, task['stage'])
                    target = item['target']
        self.locations[key] = target
        self.allocate(request, task, target)

    def schedule_one(self, request, tid):
        original = self.tasks[tid]
        if original['op'] == 'expert_pack':
            self.resolve(request, original)
        task = self.view(request, tid)
        if 'expert' in task:
            assert self.invocation(request, task) in self.slots
            if self.memory_partition(task) != self.home(task):
                assert (task['layer'], task['expert']) in self.resident
        self.tasks[tid] = task
        old_flows = self.semantic_flows
        if task['op'] == 'expert_combine':
            phase, layer = task['stage'], task['layer']
            self.semantic_flows = [dict(row, expert_cluster=self.locations.get(
                (request, phase, layer, row['expert']), row['expert_cluster']))
                if row['phase'] == phase and row['layer'] == layer else row for row in old_flows]
        try:
            result = super().schedule_one(request, tid)
        finally:
            self.tasks[tid] = original
            self.semantic_flows = old_flows
        row = self.task_rows[-1]
        if 'expert' in task:
            slot = self.slots[self.invocation(request, task)]
            row['execution_workspace_base'] = slot['base_address']
            weight = task.get('weight_key')
            if weight:
                source = self.plan['weight_addresses'][weight]
                item = self.plan['replica_by_key'].get(f"{task['layer']}:{task['expert']}")
                address = source['base_address']
                if self.memory_partition(task) != source['partition']:
                    address = next(w['target_address'] for w in item['weights'] if w['key'] == weight)
                assert address % 8192 == source['base_address'] % 8192
                row['execution_weight_base'] = address
        if task['op'] == 'expert_combine':
            for key, slot in self.slots.items():
                if key[:3] == (request, task['stage'], task['layer']):
                    assert slot['release_ns'] is None
                    slot['release_ns'] = result
                    self.slot_free[slot['partition']][slot['slot']] = result
        return result

    def run(self):
        self.prelude()
        waiting = {}
        ready = []
        for request in range(self.requests):
            for tid, task in self.tasks.items():
                waiting[request, tid] = len(task['deps'])
                if not task['deps']:
                    ready.append((request, tid))
        while ready:
            default = min(ready, key=lambda key: (self.earliest(key), key))
            chosen = self.online.choose_task(self, ready, default)
            if chosen is None:
                continue
            ready.remove(chosen)
            request, tid = chosen
            self.cursor = max([self.cursor] + [self.done[request, dep]['end_ns'] for dep in self.tasks[tid]['deps']])
            self.cursor += self.plan['task_decision_ns']
            self.schedule_one(request, tid)
            for child in self.children[tid]:
                waiting[request, child] -= 1
                if waiting[request, child] == 0:
                    ready.append((request, child))
        assert len(self.task_rows) == self.requests * len(self.tasks)
        assert sum(r['MAC'] for r in self.task_rows) == self.requests * self.mac_per_request
        assert all(slot['release_ns'] is not None for slot in self.slots.values())
        if self.mechanism == 'dynamic_copy_control':
            assert self.triggered_controls == set(self.copy_control)
        return max(row['end_ns'] for row in self.task_rows)

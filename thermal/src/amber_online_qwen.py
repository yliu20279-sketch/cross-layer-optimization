"""Causal Qwen adaptation of AMBER's two online control stages.

The ready-task choice and per-region OPP decision use the unchanged 1292-state
HotSpot-derived RC plant. The bounded candidate solver and voltage ratios are
MODELED, not author-supplied RTL. Native 0.5/0.75/1.0 task profiles preserve
the fixed DRAM/NoC clocks and recompute NPU-cycle progress at each OPP.
"""
from __future__ import annotations

import math
import hashlib
from collections import Counter, defaultdict

import numpy as np
from scipy.sparse import eye
from scipy.sparse.linalg import splu

from graph_scheduler import PREP, PARENT, ImplicitPlant, load, thermal_bank
from op_thermal import ThermalPlant
from sota_compare import Network


class QwenAmberOnline:
    def __init__(self, scenario, mapping, config, operating_point=None):
        self.config = config["online"]
        self.scenario = scenario
        self.mapping = mapping
        demand = load("meta_sota_demand_intensity_1req.json")
        assert demand["source_profile_sha256"] == hashlib.sha256(
            (PREP / "gtp_srs_native_task_profiles.json").read_bytes()).hexdigest()
        self.demand = demand["by_op"]
        self.dt_ns = int(self.config["power_bin_ms"] * 1e6)
        assert self.dt_ns == 1_000_000
        self.operating_point = operating_point
        self.op_folder = (PREP/"operating_point_2ghz_rconv3"
                          if operating_point == "2ghz_rconv3" else None)
        if operating_point is not None and self.op_folder is None:
            raise ValueError("Unknown thermal operating point")
        self.plant = (ThermalPlant(scenario["thermal"]["initial_C"],
                                   self.op_folder/"rc") if self.op_folder
                      else ImplicitPlant(scenario["thermal"]["initial_C"]))
        self.temperature = np.full(96, scenario["thermal"]["initial_C"])
        self._h = self.dt_ns*1e-9/2
        self._solve = splu(eye(len(self.plant.state),format="csc")-
                           self._h*self.plant.A).solve
        first = self._solve((self._h*self.plant.B).toarray())
        self._next_impulse = first+self._solve(first)
        self._impulse = []
        self._baseline_rows = []
        self._baseline_end = 0
        self._baseline_tail = self.plant.state.copy()
        self.static = np.zeros(96)
        p = scenario["power"]
        self.static[:16] = (p["core_static_W"] + p["lbuf_leak_W"] +
                            p["router_static_W"] + p["ni_static_W"])
        self.static[16:32] = p["sram_leak_W"]
        import json
        curves = json.loads((PARENT / "prepared/memory_curves.json").read_text())
        self.static[32:] = curves["1"]["idle_W_per_partition"] / 4
        self.current_bin = 0
        self.seen = 0
        self.energy_by_bin = defaultdict(lambda: np.zeros(96))
        self.opp_profiles = {}
        if self.op_folder is not None:
            native = json.loads((self.op_folder/
                                 "gtp_srs_native_opp_profiles.json").read_text())
            assert native["status"] == "NATIVE_2GHZ_THREE_OPP_PASS_BOUNDED_DRAM"
            self.opp_profiles = {ratio:native["profiles"][str(ratio)]
                                 for ratio in (0.75,0.5)}
        else:
            for ratio in (0.75, 0.5):
                suffix = str(ratio).replace(".", "p")
                native = load(f"gtp_srs_native_task_profiles_opp{suffix}.json")
                assert native["opp_ratio"] == ratio
                self.opp_profiles[ratio] = native["profiles"]
        self.voltages = dict(zip(map(float,self.config["frequency_ratios"]),
                                 map(float,self.config["voltage_ratios"])))
        self.stage1 = Counter()
        self.stage2 = Counter()
        self.rows = []
        self.stage1_rows = []
        self.last_opp = {cluster:1.0 for cluster in range(16)}

    def begin_cohort(self, start_ns):
        assert not self.energy_by_bin
        assert abs(start_ns/self.dt_ns-round(start_ns/self.dt_ns))<1e-7
        assert self.current_bin == int(round(start_ns/self.dt_ns))
        self.seen=0
        self.rows = []
        self.stage1_rows = []

    def observe(self, sim):
        for start, end, energy, _ in sim.intervals[self.seen:]:
            if end <= start:
                raise AssertionError("nonpositive energy interval")
            for b in range(int(start // self.dt_ns), int(math.ceil(end/self.dt_ns))):
                overlap = max(0., min(end,(b+1)*self.dt_ns)-max(start,b*self.dt_ns))
                if overlap:
                    if b < self.current_bin:
                        raise AssertionError("retroactive online energy")
                    self.energy_by_bin[b] += energy * (overlap/(end-start))
        if self.seen != len(sim.intervals):
            self._invalidate_baseline()
        self.seen = len(sim.intervals)

    def _invalidate_baseline(self):
        self._baseline_rows = []
        self._baseline_end = self.current_bin
        self._baseline_tail = self.plant.state.copy()

    def _ensure_impulse(self, count):
        while len(self._impulse) < count:
            self._impulse.append(np.asarray(self.plant.C@self._next_impulse))
            self._next_impulse = self._solve(self._solve(self._next_impulse))

    def _step_state(self, state, power):
        forcing = self._h*(self.plant.B@power)
        state = self._solve(state+forcing)
        return self._solve(state+forcing)

    def advance(self, ns):
        while (self.current_bin+1)*self.dt_ns <= ns + 1e-7:
            self.temperature = self.plant.step(
                self.static + self.energy_by_bin.pop(self.current_bin,
                                                      np.zeros(96))*1000)
            self.current_bin += 1
            self._invalidate_baseline()

    def _earliest(self, sim, key):
        request, tid = key
        task = sim.tasks[tid]
        return max([sim.done[request,dep]["end_ns"] for dep in task["deps"]] +
                   [sim.array_free[sim.cluster(task)],
                    sim.partition_free[sim.memory_partition(task)],sim.cursor])

    def choose_task(self, sim, ready, default):
        self.observe(sim)
        earliest = self._earliest(sim, default)
        # Resource availability can be later than the causal release frontier.
        # Advancing to `earliest` here would make subsequently emitted NoC
        # transfers appear retroactive, even though they start at sim.cursor.
        self.advance(sim.cursor)
        self.stage1["decisions"] += 1
        # Same RC-constrained ready-subtask evaluation as the pi0.5 controller.
        # Do not bypass the search merely because the current state is cool.
        eligible = sorted((key for key in ready
                           if self._earliest(sim,key) <= earliest+self.dt_ns),
                          key=lambda key:(self._earliest(sim,key),key))
        eligible = eligible[:self.config["ready_candidates"]]
        scored = []
        for key in eligible:
            task = sim.tasks[key[1]]
            region = sim.cluster(task)
            bank = sim.memory_partition(task)
            intensity = float(self.demand[task["op"]]["intensity"])
            assert -1 <= intensity <= 1
            start = self._earliest(sim,key)
            forecast = self._forecast(sim,task,region,bank,start,1.0)
            scored.append((key,start,forecast,intensity))
        self.stage1["thermal_candidate_evaluations"] += len(eligible)
        feasible = [row for row in scored if row[2]["safe"]]
        if feasible:
            chosen = min(feasible,key=lambda row:(row[2]["cost"],row[1],
                                                  abs(row[3]+sim.last_intensity),
                                                  row[0]))[0]
            self.stage1["feasible"] += 1
        else:
            chosen = min(scored,key=lambda row:(row[2]["peak_C"],row[1],row[0]))[0]
            self.stage1["fallback"] += 1
        self.stage1["reordered"] += int(chosen != default)
        selected = next(row for row in scored if row[0] == chosen)
        self.stage1_rows.append(dict(decision_ns=float(sim.cursor),
                                     request=chosen[0],task_id=chosen[1],
                                     considered=len(scored),admissible=len(feasible),
                                     predicted_peak_C=selected[2]["peak_C"],
                                     predicted_cost=selected[2]["cost"],
                                     offline_intensity=selected[3],
                                     fallback=int(not bool(feasible)),
                                     reordered=int(chosen != default)))
        return chosen

    def _candidate_energy(self, sim, task, compute, partition, ratio):
        activity = np.asarray(sim.profile(task,ratio)["activity"],float)
        p = sim.sc["power"]
        peak = sim.sc["activity_model"]["peak_fp16_MAC_per_cycle_per_cluster"]
        freq = sim.sc["activity_model"]["npu_frequency_Hz"]
        energy = np.zeros(96)
        energy[compute] += (activity[0]/(peak*freq)*p["core_dynamic_full_W"]*
                            self.voltages[ratio]**2)
        energy[compute] += (activity[3]*p["lbuf_read_pJ_access"]+
                            activity[4]*p["lbuf_write_pJ_access"])*1e-12
        energy[partition] += activity[5:13].sum()*8*p["hb_pJ_per_bit"]*1e-12
        energy[16+compute] += (activity[1]*p["sram_read_pJ_access"]+
                               activity[2]*p["sram_write_pJ_access"])*1e-12
        idle = self.static[32+thermal_bank(partition,0)]*activity[18]*1e-9
        for bank in range(4):
            energy[32+thermal_bank(partition,bank)] += max(0.,activity[13+bank]-idle)
        return energy

    def _forecast(self, sim, task, compute, partition, start, ratio):
        profile = sim.profile(task,ratio)
        duration = float(profile["duration_ns"])
        end = start+duration
        energy = self._candidate_energy(sim,task,compute,partition,ratio)
        events = [(float(start),float(end),energy)]
        if partition != compute:
            bytes_out = int(round(sum(profile["activity"][9:13])))
            if bytes_out:
                preview = Network(sim.sc)
                preview.links = sim.net.links.copy()
                egress_end = preview.transfer(compute,partition,bytes_out,end,
                                              "amber_remote_HB_write",(-1,-1),
                                              "full_global")
                flow = preview.flows[-1]
                flits = math.ceil(bytes_out/sim.sc["timing"]["noc_flit_bytes"])
                p = sim.sc["power"]
                egress_energy = np.zeros(96)
                path = [int(node) for node in flow["path"].split("-")]
                for router in path[:-1]:
                    egress_energy[router] += flits*p["router_pJ_flit_hop"]*1e-12
                egress_energy[compute] += flits*p["ni_pJ_endpoint_flit"]*1e-12
                egress_energy[partition] += flits*p["ni_pJ_endpoint_flit"]*1e-12
                events.append((float(flow["start_ns"]),float(egress_end),
                               egress_energy))
        base = self.current_bin
        first = max(base,int(start//self.dt_ns))
        latest_committed = max(self.energy_by_bin, default=base)
        last = max(int(math.ceil(max(event[1] for event in events)/self.dt_ns)),
                   latest_committed+1) + int(self.config["lookahead_bins"])
        self._ensure_impulse(last-first)
        state = self._baseline_tail
        for b in range(self._baseline_end,last):
            power = self.static+self.energy_by_bin.get(b,np.zeros(96))*1000
            state = self._step_state(state,power)
            self._baseline_rows.append(
                np.asarray(self.plant.ambient+self.plant.C@state))
        self._baseline_end = last
        self._baseline_tail = state
        delta = np.zeros((last-first,96))
        for event_start,event_end,event_energy in events:
            event_duration = event_end-event_start
            response = [kernel@event_energy
                        for kernel in self._impulse[:last-first]]
            begin = max(first,int(event_start//self.dt_ns))
            finish = min(last,int(math.ceil(event_end/self.dt_ns)))
            for source in range(begin,finish):
                overlap = max(0.,min(event_end,(source+1)*self.dt_ns)-
                              max(event_start,source*self.dt_ns))
                if overlap:
                    factor = (overlap/event_duration)*1000
                    for target_bin in range(source,last):
                        delta[target_bin-first] += response[target_bin-source]*factor
        rows = np.asarray(self._baseline_rows[first-base:last-base])+delta
        peaks = np.max(rows,axis=1)
        limit = float(self.config["thermal_max_C"]-
                      self.config["safety_guard_C"])
        target = float(self.config["thermal_target_C"])
        return dict(peak_C=max(float(self.temperature.max()),
                               float(np.max(peaks))),
                    cost=float(np.square(peaks-target).sum()),
                    safe=bool(np.all(peaks<=limit)))

    def choose_opp(self, sim, task, compute, partition, ready, request=None):
        self.observe(sim)
        start = max(ready,sim.array_free[compute],sim.partition_free[partition])
        self.advance(sim.cursor)
        self.stage2["decisions"] += 1
        defer_bins=0
        forecasts={}
        ratio = None
        for offset in range(int(self.config["max_defer_bins"])+1):
            trial_start=start+offset*self.dt_ns
            for candidate in (1.0,0.75,0.5):
                self.stage2["thermal_forecasts"] += 1
                forecast=self._forecast(sim,task,compute,partition,
                                        trial_start,candidate)
                forecasts[f"{offset}:{candidate:g}"]=forecast["peak_C"]
                if forecast["safe"]:
                    ratio = candidate
                    defer_bins=offset
                    break
            if ratio is not None:
                break
        if ratio is None:
            raise RuntimeError("No safe native OPP within configured deferral bound")
        self.stage2["deferred_1ms_bins"] += defer_bins
        self.stage2[f"opp_{ratio:g}"] += 1
        previous=self.last_opp[compute]
        if previous != ratio:
            self.stage2["opp_switches"] += 1
        self.last_opp[compute]=ratio
        self.rows.append(dict(request=request,task_id=task["task_id"],
                              op=task["op"],cluster=compute,
                              decision_ns=float(sim.cursor),
                              scheduled_start_ns=float(start+defer_bins*self.dt_ns),
                              observed_peak_C=float(self.temperature.max()),
                              previous_opp=previous,chosen_opp=ratio,
                              voltage_ratio=self.voltages[ratio],
                              forecast_1p0_C=forecasts.get(f"{defer_bins}:1"),
                              forecast_0p75_C=forecasts.get(f"{defer_bins}:0.75"),
                              forecast_0p5_C=forecasts.get(f"{defer_bins}:0.5"),
                              deferred_bins=defer_bins))
        return ratio,self.voltages[ratio],start+defer_bins*self.dt_ns

    def report(self):
        return dict(stage1=dict(self.stage1),stage2=dict(self.stage2),
                    online_final_bin=self.current_bin,
                    online_peak_completed_bin_C=float(self.temperature.max()),
                    controller_scope="MODELED bounded RC-predictive Stage1 and "
                    "highest-safe-native-OPP Stage2; no cool-state bypass")

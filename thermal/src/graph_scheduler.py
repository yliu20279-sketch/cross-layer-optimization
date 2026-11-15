"""Causal Qwen-MoE task/XY scheduler for baseline and semantic-only diagnostics.

`semantic_only` and `sor_diagnostic` are deliberately NOT called `meta_sota`:
HiBAND GTP/HIC and AMBER online thermal OPP must still be composed. All
diagnostics need native profiles hashed to this exact address layout.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
from portable import RUNTIME, INPUT
PARENT = RUNTIME
PREP = INPUT / "prepared"
sys.path.insert(0, str(PARENT))
from backend import thermal_bank  # noqa: E402
from sota_compare import Network, render_trace  # noqa: E402
from implicit_thermal import ImplicitPlant  # noqa: E402

COMPONENTS = ["CORE", "SRAM", "LBUF", "Router", "NI", "HB", "DRAM"]


def load(name):
    return json.loads((PREP / name).read_text())


class Scheduler:
    def __init__(self, policy, requests, compute_mapping=None,
                 online_controller=None, operating_point=None,
                 start_ns=0.0, event_execution_folder=None, native_layout=None):
        if policy not in ("baseline", "semantic_only", "sor_diagnostic",
                          "gtp_head_diagnostic", "gtp_barrier_diagnostic",
                          "gtp_sor_diagnostic", "gtp_srs_diagnostic",
                          "gtp_srs_sor_diagnostic"):
            raise ValueError(policy)
        self.policy = policy
        self.native_layout = (json.loads(Path(native_layout).read_text()) if native_layout is not None else None)
        if self.native_layout is not None:
            if policy!='baseline' or requests!=32 or event_execution_folder is None:
                raise ValueError('32-slot physical placement requires the full native event backend')
            assert self.native_layout['status']=='PHYSICAL_32_SLOT_REPLACEMENT_CAPACITY_PASS_NO_TIMING_CLAIM'
            assert self.native_layout['requests']==requests
            assert self.native_layout['aggregate_DRAM_bytes']==32*2**30
        self.requests = requests
        self.online = online_controller
        self.compute_mapping = (list(range(16)) if compute_mapping is None
                                else list(map(int, compute_mapping)))
        if sorted(self.compute_mapping) != list(range(16)):
            raise ValueError("AMBER compute mapping must permute the 16 fixed clusters")
        self.layout_policy = "baseline" if policy == "baseline" else "meta_sota"
        self.profile_policy = ("meta_sota" if policy == "sor_diagnostic"
                               else "gtp_srs_sor" if policy == "gtp_srs_sor_diagnostic"
                               else "gtp_srs" if policy == "gtp_srs_diagnostic"
                               else "gtp_sor" if policy == "gtp_sor_diagnostic"
                               else "gtp_hic" if policy in ("gtp_head_diagnostic",
                                                           "gtp_barrier_diagnostic")
                               else policy)
        source = ("gtp_barrier_manifest.json" if policy == "gtp_barrier_diagnostic"
                  else "gtp_srs_sor_manifest.json" if policy == "gtp_srs_sor_diagnostic"
                  else "gtp_srs_manifest.json" if policy == "gtp_srs_diagnostic"
                  else "gtp_sor_manifest.json" if policy == "gtp_sor_diagnostic"
                  else "gtp_hic_manifest.json" if policy == "gtp_head_diagnostic"
                  else "sor_manifest.json" if policy == "sor_diagnostic"
                  else "manifest.json")
        manifest = load(source)
        self.tasks = {t["task_id"]: t for t in manifest["tasks"]}
        self.mac_per_request = manifest["theoretical_MAC"]
        gtp = policy in ("gtp_head_diagnostic", "gtp_barrier_diagnostic",
                         "gtp_sor_diagnostic", "gtp_srs_diagnostic",
                         "gtp_srs_sor_diagnostic")
        joint = policy == "gtp_sor_diagnostic"
        joint_srs_sor = policy == "gtp_srs_sor_diagnostic"
        self.srs = policy in ("gtp_srs_diagnostic", "gtp_srs_sor_diagnostic")
        native = load("gtp_srs_sor_native_task_profiles.json" if joint_srs_sor else
                      "gtp_srs_native_task_profiles.json" if self.srs else
                      "gtp_sor_native_task_profiles.json" if joint else
                      "gtp_native_task_profiles.json" if gtp
                      else "native_task_profiles.json")
        expected_status = ("GTP_SRS_SOR_NATIVE_PROFILE_PASS_BOUNDED_CONTEXT"
                           if joint_srs_sor else
                           "GTP_SRS_NATIVE_PROFILE_PASS_BOUNDED_CONTEXT" if self.srs
                           else "GTP_SOR_NATIVE_PROFILE_PASS_BOUNDED_CONTEXT" if joint
                           else "GTP_NATIVE_PROFILE_PASS_BOUNDED_CONTEXT" if gtp
                           else "NATIVE_PROFILE_PASS_BOUNDED_CONTEXT")
        if native["status"] != expected_status:
            raise RuntimeError("Native task profiles incomplete")
        if policy == "gtp_barrier_diagnostic":
            base_hash = hashlib.sha256((PREP / "gtp_hic_manifest.json").read_bytes()).hexdigest()
            if manifest.get("base_manifest_sha256") != base_hash:
                raise RuntimeError("GTP barrier is stale against its native-profiled base graph")
        hash_source = ("gtp_hic_manifest.json" if policy == "gtp_barrier_diagnostic"
                       else source)
        manifest_hash = (native.get("manifest_sha256") if gtp else
                         native.get("manifest_sha256", {}).get(self.profile_policy))
        if manifest_hash != \
                hashlib.sha256((PREP / hash_source).read_bytes()).hexdigest():
            raise RuntimeError("Native profile was built from a stale task graph")
        files = (("gtp_srs_sor_addresses.json", "address_sha256"),
                 ("gtp_srs_sor_capacity.json", "capacity_sha256"),
                 ("gtp_srs_sor_logical_wave_profiles.json", "native_memory_profile_sha256")) if joint_srs_sor else (("gtp_srs_addresses.json", "address_sha256"),
                 ("gtp_srs_capacity.json", "capacity_sha256"),
                 ("gtp_srs_logical_wave_profiles.json", "native_memory_profile_sha256")) if self.srs else ((
                 "gtp_sor_addresses.json", "address_sha256"),
                 ("gtp_sor_capacity.json", "capacity_sha256"),
                 ("gtp_sor_logical_wave_profiles.json", "native_memory_profile_sha256")) if joint else ((
                 "gtp_hic_addresses.json", "address_sha256"),
                 ("gtp_hic_capacity.json", "capacity_sha256"),
                 ("gtp_logical_wave_profiles.json", "native_memory_profile_sha256")) if gtp else (
                 ("tensor_addresses.json", "address_sha256"),
                 ("capacity.json", "capacity_sha256"),
                 ("moe_logical_wave_profiles.json", "native_memory_profile_sha256"))
        for filename, field in files:
            if native.get(field) != hashlib.sha256((PREP / filename).read_bytes()).hexdigest():
                raise RuntimeError("Native profile was built from a stale address layout")
        self.profiles = native["profiles"]
        self.profile_keys = (native["task_profile_keys"] if gtp else
                             native["task_profile_keys"][self.profile_policy])
        self.operating_point = operating_point
        self.op_folder = None
        self.opp_profiles = {}
        if operating_point is not None:
            if operating_point != "2ghz_rconv3" or policy not in (
                    "baseline", "gtp_srs_diagnostic"):
                raise ValueError("Unsupported operating point or unprofiled policy")
            self.op_folder = PREP / "operating_point_2ghz_rconv3"
            stem = "baseline" if policy == "baseline" else "gtp_srs"
            rebuilt = json.loads(
                (self.op_folder/f"{stem}_native_opp_profiles.json").read_text())
            if rebuilt["status"] != "NATIVE_2GHZ_THREE_OPP_PASS_BOUNDED_DRAM":
                raise RuntimeError("Incomplete native OPP profile set")
            from build_native_profiles import SRAM_RESIDENCY_POLICY
            if (rebuilt.get('sram_residency_policy') != SRAM_RESIDENCY_POLICY or
                rebuilt.get('residency_implementation_sha256') != hashlib.sha256(
                    (HERE/'build_native_profiles.py').read_bytes()).hexdigest()):
                raise RuntimeError('Native OPP profiles use stale/unbounded SRAM residency')
            if rebuilt["source_profile_sha256"] != hashlib.sha256(
                    (PREP/("native_task_profiles.json" if policy == "baseline"
                           else "gtp_srs_native_task_profiles.json")).read_bytes()).hexdigest():
                raise RuntimeError("Native OPP profile source changed")
            assert rebuilt["task_profile_keys"] == self.profile_keys
            self.opp_profiles = {float(k): v for k,v in rebuilt["profiles"].items()}
            self.profiles = self.opp_profiles[1.0]
        self.placement = load("placement.json")
        self.semantic_flows = load("semantic_flows.json")[self.layout_policy]
        self.routing = load("routing.json")
        self.sc = json.loads((PARENT / "modeled_scenario.json").read_text())
        if self.op_folder is not None:
            path = self.op_folder / "scenario.json"
            self.sc = json.loads(path.read_text())
            if rebuilt["scenario_sha256"] != hashlib.sha256(path.read_bytes()).hexdigest():
                raise RuntimeError("Native OPP profile scenario changed")
            if rebuilt["thermal_rc_A_sha256"] != hashlib.sha256(
                    (self.op_folder/"rc/A.csv").read_bytes()).hexdigest():
                raise RuntimeError("Rconv=3 RC operator changed")
        self.memory_curves = json.loads((PARENT / "prepared/memory_curves.json").read_text())
        self.kv_slots = None
        if requests <= 4:
            address_book = load(files[0][0])
            if files[0][0] == "tensor_addresses.json":
                address_book = address_book[self.layout_policy]
            self.kv_slots = {}
            for name, entry in address_book.items():
                if ":kv:" not in name:
                    continue
                stride = int(entry["request_slot_stride_bytes"])
                assert entry["size_bytes"] == 4 * stride
                bases = [int(entry["base_address"] + slot * stride)
                         for slot in range(requests)]
                assert len(set(bases)) == requests
                assert all(base % 8192 == bases[0] % 8192 for base in bases)
                self.kv_slots[name] = bases
        if requests > 4:
            if self.native_layout is not None:
                self.kv_slots=self.native_layout['kv_base_by_slot']
                self.placement=self.native_layout['placement']
            elif self.op_folder is None or requests != 16:
                raise ValueError("Only the audited 16-slot 2-GHz layout is supported")
            else:
                slots = json.loads((self.op_folder/"request_slots_16.json").read_text())
                assert slots["status"] == "PHYSICAL_16_SLOT_CAPACITY_PASS_NO_TIMING_CLAIM"
                assert slots["capacity_sha256"] == hashlib.sha256((PREP/"capacity.json").read_bytes()).hexdigest()
                assert slots["addresses_sha256"] == hashlib.sha256((PREP/"tensor_addresses.json").read_bytes()).hexdigest()
                assert slots["meta_capacity_sha256"] == hashlib.sha256((PREP/"gtp_srs_capacity.json").read_bytes()).hexdigest()
                assert slots["meta_addresses_sha256"] == hashlib.sha256((PREP/"gtp_srs_addresses.json").read_bytes()).hexdigest()
                assert self.sc["timing"]["dram_bank_interleave_bytes"] == 2048
                self.kv_slots = slots[self.layout_policy]["kv_base_by_slot"]
        self.m = SimpleNamespace(sc=self.sc,
                                 memory=SimpleNamespace(curves=self.memory_curves))
        self.net = Network(self.sc)
        self.array_free = np.full(16,float(start_ns))
        self.partition_free = np.full(16,float(start_ns))
        self.intervals = []
        self.task_rows = []
        self.done = {}
        self.cursor = float(start_ns)
        self.last_intensity = 0.0
        self.scatter_ready = {}
        self.children = defaultdict(list)
        for tid, task in self.tasks.items():
            for parent in task["deps"]:
                self.children[parent].append(tid)
        self.flow_index = defaultdict(list)
        self.srs_home_norm = {(t["stage"],t["layer"],t["primary_cluster"]): tid
                              for tid,t in self.tasks.items()
                              if t["op"] == "srs_home_norm"}
        self.tokens_at_home = defaultdict(Counter)
        self.event_execution = None
        for row in self.semantic_flows:
            self.flow_index[(row["phase"], row["layer"], row["expert"])].append(row)
        for phase, ids in (("prefill", self.routing["token_ids"]),
                           ("decode", self.routing["decode_token_ids"])):
            for layer in range(24):
                for token, token_id in enumerate(ids):
                    home = (token % 16 if policy == "baseline" else
                            self.placement["meta_token_class_home"][layer][token_id % 16])
                    self.tokens_at_home[(phase, layer)][home] += 1
        if event_execution_folder is not None:
            from event_execution import QwenEventExecution
            self.event_execution = QwenEventExecution(self,event_execution_folder)

    def memory_partition(self, task):
        if "expert" not in task:
            return task["primary_cluster"]
        placement = (self.placement["baseline_expert_cluster"] if
                     self.policy == "baseline" else
                     self.placement["meta_expert_cluster"])
        return placement[task["layer"]][task["expert"]]

    def cluster(self, task):
        return self.compute_mapping[self.memory_partition(task)]

    def profile(self, task, ratio=1.0):
        profiles = (self.profiles if ratio == 1.0 else
                    self.opp_profiles[ratio] if self.op_folder is not None else
                    self.online.opp_profiles[ratio])
        return profiles[self.profile_keys[str(task["task_id"])]]

    def task_energy(self, activity, cluster, partition, start, end,
                    voltage=1.0):
        sc = self.sc
        p = sc["power"]
        peak = sc["activity_model"]["peak_fp16_MAC_per_cycle_per_cluster"]
        freq = sc["activity_model"]["npu_frequency_Hz"]
        a = np.asarray(activity, float)
        core = a[0] / (peak * freq) * p["core_dynamic_full_W"] * voltage**2
        sram = (a[1] * p["sram_read_pJ_access"] +
                a[2] * p["sram_write_pJ_access"]) * 1e-12
        lbuf = (a[3] * p["lbuf_read_pJ_access"] +
                a[4] * p["lbuf_write_pJ_access"]) * 1e-12
        hb = a[5:13].sum() * 8 * p["hb_pJ_per_bit"] * 1e-12
        idle = self.memory_curves["1"]["idle_W_per_partition"] * a[18] * 1e-9 / 4
        dram = np.maximum(0.0, a[13:17] - idle)
        energy = np.zeros(96)
        energy[cluster] += core + lbuf
        energy[partition] += hb
        energy[16 + cluster] += sram
        for bank in range(4):
            energy[32 + thermal_bank(partition, bank)] += dram[bank]
        component = np.asarray([core, sram, lbuf, 0., 0., hb, dram.sum()])
        assert abs(energy.sum() - component.sum()) < 1e-9
        self.intervals.append((start, end, energy, component))

    def flow_energy(self, first):
        p = self.sc["power"]
        flit_bytes = self.sc["timing"]["noc_flit_bytes"]
        for flow in self.net.flows[first:]:
            flits = math.ceil(flow["bytes"] / flit_bytes)
            path = [int(node) for node in flow["path"].split("-")]
            energy = np.zeros(96)
            for router in path[:-1]:
                energy[router] += flits * p["router_pJ_flit_hop"] * 1e-12
            energy[flow["src"]] += flits * p["ni_pJ_endpoint_flit"] * 1e-12
            energy[flow["dst"]] += flits * p["ni_pJ_endpoint_flit"] * 1e-12
            component = np.zeros(7)
            component[3] = flits * flow["hops"] * p["router_pJ_flit_hop"] * 1e-12
            component[4] = 2 * flits * p["ni_pJ_endpoint_flit"] * 1e-12
            assert abs(energy.sum() - component.sum()) < 1e-9
            if self.event_execution is not None:
                self.event_execution.record_energy(flow['start_ns'],flow['end_ns'],energy,component)
            else:
                self.intervals.append((flow["start_ns"], flow["end_ns"],
                                       energy, component))

    def send(self, src, dst, size, ready, kind, key):
        first = len(self.net.flows)
        finish = self.net.transfer(src, dst, size, ready, kind, key,
                                   "full_global")
        self.flow_energy(first)
        return finish

    def ensure_scatter(self, request, phase, layer, owner, ready):
        key = (request, phase, layer)
        if key in self.scatter_ready:
            return self.scatter_ready[key]
        times = {}
        for home, count in self.tokens_at_home[phase, layer].items():
            if self.srs:
                source = self.done[request, self.srs_home_norm[phase,layer,home]]
                scattered = max(source["end_ns"], ready)
            else:
                scattered = self.send(owner, self.compute_mapping[home], 2 * 2048 * count,
                                      max(ready, self.cursor), "token_scatter",
                                      (request, -1))
            times[home] = self.send(owner, self.compute_mapping[home], 4 * 4 * count,
                                    scattered, "top4_indices", (request, -1))
        self.scatter_ready[key] = times
        return times

    def schedule_one(self, request, tid):
        task = self.tasks[tid]
        cluster = self.cluster(task)
        partition = self.memory_partition(task)
        ready = max([self.done[request, dep]["end_ns"] for dep in task["deps"]]
                    + [self.cursor])
        if self.event_execution is not None:
            # Tensor dependencies resolve to persistent producer versions.
            # The event backend executes the actual operand NoC transfers;
            # legacy full-task transfers would double-charge these bytes.
            opp,voltage,defer = (self.online.choose_opp(self,task,cluster,partition,ready,request)
                                if self.online is not None else (1.0,1.0,ready))
            return self.event_execution.admit(request,tid,max(ready,defer),opp,voltage)
        if task["op"] == "srs_reduce_scatter_residual":
            count = task["srs_token_count"]
            for dep in task["deps"]:
                if dep in task.get("control_deps", []):
                    continue
                source = self.done[request, dep]
                kind = ("srs_residual" if dep == task["srs_residual_dep"]
                        else "srs_partial")
                ready = max(ready, self.send(source["cluster"], cluster,
                    2 * count * 2048, max(source["end_ns"],self.cursor),
                    kind, (request,tid)))
        elif task["op"] == "expert_pack":
            times = self.ensure_scatter(request, task["stage"], task["layer"],
                                        self.compute_mapping[task["primary_cluster"]], ready)
            for row in self.flow_index[task["stage"], task["layer"], task["expert"]]:
                src = self.compute_mapping[row["source_cluster"]]
                ready = max(ready, self.send(src, cluster, row["dispatch_bytes"],
                          max(times[row["source_cluster"]], self.cursor), "expert_dispatch",
                          (request, tid)))
        elif task["op"] == "expert_combine":
            homes = self.tokens_at_home[task["stage"], task["layer"]]
            arrival = {home: ready for home in homes}
            for row in self.semantic_flows:
                if row["phase"] != task["stage"] or row["layer"] != task["layer"]:
                    continue
                src = self.compute_mapping[row["expert_cluster"]]
                dst = self.compute_mapping[row["source_cluster"]]
                home = row["source_cluster"]
                arrival[home] = max(arrival[home], self.send(src, dst,
                    row["combine_bytes"], max(ready, self.cursor),
                    "expert_return", (request, tid)))
            for home, count in homes.items():
                ready = max(ready, self.send(self.compute_mapping[home], cluster,
                    2 * 2048 * count,
                    max(arrival[home], self.cursor),
                    "sag_after_moe" if self.srs else "token_gather",
                    (request, tid)))
        else:
            for dep in task["deps"]:
                source = self.done[request, dep]
                src = source["cluster"]
                if src == cluster or dep in task.get("control_deps", []):
                    continue
                size = self.tasks[dep].get(
                    "noc_output_bytes", self.tasks[dep]["write_bytes"])
                if (self.tasks[dep].get("weight_key", "").endswith(":v") and
                    task["stage"] == "decode" and
                    task["op"].startswith("moe_activation_mm_1_513_")):
                    size = 2 * 128  # one value head, not all 16 heads
                if task["layer"] == 24 and "shape" in task:
                    size = min(size, 2 * 2048)  # only last token for logits
                flow_kind = ("sor_residual_history" if
                             self.tasks[dep]["op"] == "residual_history_fetch"
                             else "srs_attention_out_gather" if
                             task["op"] == "srs_attention_out_gather"
                             else "srs_shared_input_gather" if
                             task["op"] == "srs_shared_input_gather"
                             else "gtp_input_broadcast" if
                             task["op"] == "gtp_input_stage"
                             else "gtp_head_gather" if
                             self.policy in ("gtp_head_diagnostic",
                                             "gtp_barrier_diagnostic",
                                             "gtp_sor_diagnostic",
                                             "gtp_srs_diagnostic",
                                             "gtp_srs_sor_diagnostic") and
                             task["op"] == "concat_heads"
                             else "core_core")
                ready = max(ready, self.send(src, cluster,
                    max(self.sc["timing"]["noc_flit_bytes"], size),
                    max(source["end_ns"], self.cursor), flow_kind,
                    (request, tid)))
        # OPP selection must see the actual arrival of remote HB input.
        # DMA byte activity is invariant across the native OPP profiles.
        if partition != cluster:
            nominal_activity = self.profile(task, 1.0)["activity"]
            read_bytes = int(round(sum(nominal_activity[5:9])))
            if read_bytes:
                ready = max(ready, self.send(partition, cluster, read_bytes,
                    max(ready,self.partition_free[partition]),
                    "amber_remote_HB_read", (request,tid)))
        opp, voltage, defer_start = (self.online.choose_opp(self, task, cluster,
                                                            partition, ready, request)
                                     if self.online is not None else
                                     (1.0, 1.0, ready))
        profile = self.profile(task, opp)
        activity = profile["activity"]
        start = max(ready, defer_start, self.array_free[cluster],
                    self.partition_free[partition])
        compute_end = start + profile["duration_ns"]
        self.array_free[cluster] = compute_end
        self.partition_free[partition] = compute_end
        self.task_energy(activity, cluster, partition, start, compute_end,
                         voltage)
        end = compute_end
        if partition != cluster:
            write_bytes = int(round(sum(activity[9:13])))
            if write_bytes:
                end = self.send(cluster, partition, write_bytes, compute_end,
                                "amber_remote_HB_write", (request,tid))
                self.partition_free[partition] = end
        self.done[request, tid] = dict(end_ns=end, cluster=cluster)
        kv_bases = None
        if self.kv_slots is not None and task.get("kv_native_role"):
            role = task["kv_native_role"][-1]
            heads = ([int(task["kv_head"])] if "kv_head" in task else range(16))
            kv_bases = {}
            for head in heads:
                kv_key = f'l{task["layer"]}:kv:{role}:h{head}'
                physical_base = self.kv_slots[kv_key][request]
                assert physical_base % 8192 == self.kv_slots[kv_key][0] % 8192
                kv_bases[head] = physical_base
        self.task_rows.append(dict(request=request, task_id=tid,
                                   kv_physical_base_addresses=kv_bases,
                                   phase=task["stage"], layer=task["layer"],
                                   expert=task.get("expert", ""),
                                   op=task["op"], cluster=cluster,
                                   memory_partition=partition,
                                   opp_ratio=opp, voltage_ratio=voltage,
                                   start_ns=start, end_ns=end,
                                   MAC=task["mac_ops"],
                                   physical_read_bytes=sum(profile["activity"][5:9]),
                                   physical_write_bytes=sum(profile["activity"][9:13])))
        if self.online is not None:
            self.last_intensity = float(self.online.demand[task["op"]]["intensity"])
        return end

    def run(self):
        if self.event_execution is not None:
            return self.event_execution.run()
        waiting = {}
        ready = []
        for request in range(self.requests):
            for tid, task in self.tasks.items():
                waiting[request, tid] = len(task["deps"])
                if not task["deps"]:
                    ready.append((request, tid))
        while ready:
            chosen = min(ready, key=lambda item: (
                max([self.done[item[0], dep]["end_ns"]
                     for dep in self.tasks[item[1]]["deps"]] +
                    [self.array_free[self.cluster(self.tasks[item[1]])],
                     self.partition_free[self.memory_partition(self.tasks[item[1]])],
                     self.cursor]), item))
            if self.online is not None:
                chosen = self.online.choose_task(self, ready, chosen)
            ready.remove(chosen)
            request, tid = chosen
            earliest = max([self.done[request, dep]["end_ns"]
                            for dep in self.tasks[tid]["deps"]] + [self.cursor])
            self.cursor = earliest
            self.schedule_one(request, tid)
            for child in self.children[tid]:
                waiting[request, child] -= 1
                if waiting[request, child] == 0:
                    ready.append((request, child))
        assert len(self.task_rows) == self.requests * len(self.tasks)
        assert sum(row["MAC"] for row in self.task_rows) == \
            self.requests * self.mac_per_request
        return max(row["end_ns"] for row in self.task_rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", choices=("baseline", "semantic_only",
                                            "sor_diagnostic", "gtp_head_diagnostic",
                                            "gtp_barrier_diagnostic", "gtp_sor_diagnostic",
                                            "gtp_srs_diagnostic", "gtp_srs_sor_diagnostic"),
                        required=True)
    parser.add_argument("--requests", type=int, default=1)
    args = parser.parse_args()
    max_requests = json.loads((HERE / "experiment_config.json").read_text())[
        "kv_reserve_requests"]
    if not 1 <= args.requests <= max_requests:
        raise ValueError(f"1-{max_requests} concurrent requests fit the KV reserve")
    sim = Scheduler(args.policy, args.requests)
    makespan = sim.run()
    out = HERE / "results" / f"{args.policy}_{args.requests}req"
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("tasks.csv", sim.task_rows),
                       ("flows.csv", sim.net.flows)):
        with (out / name).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    power, components = render_trace(sim, makespan)
    assert abs(components.sum() - power.sum() * 0.001) < \
        max(1e-9, components.sum() * 1e-9)
    plant = ImplicitPlant(sim.sc["thermal"]["initial_C"])
    try:
        cold_temperature = np.asarray([plant.step(row) for row in power])
    finally:
        plant.close()
    np.savez_compressed(out / "cold_trace.npz", power_W=power,
                        temperature_C=cold_temperature,
                        components_J=components,
                        component_names=np.asarray(COMPONENTS),
                        time_bin_ms=1.)
    peak_MAC = sim.sc["activity_model"]["peak_fp16_MAC_per_cycle_per_cluster"]
    frequency = sim.sc["activity_model"]["npu_frequency_Hz"]
    utilization = args.requests * sim.mac_per_request / \
        (16 * peak_MAC * frequency * makespan * 1e-9)
    assert 0 <= utilization <= 1 + 1e-9
    summary = dict(status="COLD_DIAGNOSTIC_NOT_FULL_META_SOTA",
                   policy=args.policy, requests=args.requests,
                   makespan_ns=makespan,
                   throughput_requests_s=args.requests / (makespan * 1e-9),
                   MAC=args.requests * sim.mac_per_request,
                   DRAM_read_bytes=sum(row["physical_read_bytes"]
                                       for row in sim.task_rows),
                   DRAM_write_bytes=sum(row["physical_write_bytes"]
                                        for row in sim.task_rows),
                   NoC_bytes=sum(flow["bytes"] for flow in sim.net.flows),
                   mean_MAC_utilization=utilization,
                   cold_peak_C=float(cold_temperature.max()),
                   mean_power_W=float(power.sum(axis=1).mean()),
                   energy_J=float(components.sum()),
                   energy_conservation_error_J=float(abs(components.sum() -
                                                          power.sum()*0.001)),
                   flow_classes=dict(Counter(flow["kind"] for flow in sim.net.flows)),
                   caveat="Cold-start diagnostic only; not full meta-SOTA. "
                          "GTP head sharding appears in gtp_head/barrier/joint diagnostics; "
                          "SOR appears in sor/gtp_sor diagnostics. Full HIC local-role "
                          "alternation, Sem-MoE TP SRS/SAG, AMBER online OPP "
                          "and thermal convergence remain absent")
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

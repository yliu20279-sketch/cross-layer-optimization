"""Lower each unique Qwen-MoE task to NPUSim events and native DRAM profiles.

This remains a per-task bounded-context profile. The full graph scheduler must
subsequently reserve actual cluster, partition and XY-link resources causally.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import OrderedDict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "sustained_thermal_v35_20260914"
PREP = HERE / "prepared"
sys.path.insert(0, str(PARENT))
from backend import Generic, Memory, Shape  # noqa: E402
from task_addresses import task_address
from kv_native_regions import wave_regions as physical_kv_wave_regions


class MoEMemory(Memory):
    def __init__(self, scenario):
        curves = json.loads((PARENT / "prepared/memory_curves.json").read_text())
        super().__init__(scenario, curves)
        native = json.loads((PREP / "moe_logical_wave_profiles.json").read_text())
        if native["status"] != "PASS" or 1 not in native["completed_refresh_rates"]:
            raise RuntimeError("Nominal Qwen-native DRAM profile is not complete")
        self.wave_profiles = native["profiles"]
        self.current_task = None

    def wave(self, name, shape, w, rate, write=False, weight_base=None,
             workspace_base=4096, include_b=True):
        task = self.current_task
        if task is not None and task.get("kv_native_role"):
            key, segments = physical_kv_wave_regions(
                task, shape, w, write,
                self.sc["timing"]["dram_partition_bytes"],
                weight_base, workspace_base, task["kv_native_address_book"],
                include_b)
            return self.request_regions(key, segments, write, rate)
        return super().wave(name, shape, w, rate, write, weight_base,
                            workspace_base, include_b)

    def request_regions(self, key, segments, write, rate):
        # The SOR history fetch has no local write, and its staging task has
        # no local read. Zero-byte sides are not physical DRAM commands and
        # must not demand fabricated native profiles.
        if sum(size for _, size in segments) == 0:
            return 0.0, np.zeros(19), 0.0
        return super().request_regions(key, segments, write, rate)


SRAM_RESIDENCY_POLICY = "CAPACITY_BOUNDED_N_PANEL_M_REUSE_V1"


class CapacityBoundWeightCache:
    """FP16 B tiles; operand/output workspace is reserved separately.

    A miss is serviced into Shape's existing DMA operand slot. Retaining the
    tile beyond that slot is allowed only inside this byte-bounded cache.
    Accesses update LRU order; metadata alone never implies unlimited SRAM.
    """
    def __init__(self, capacity_bytes):
        if capacity_bytes < 0:
            raise ValueError("Native workspace exceeds physical SRAM")
        self.capacity_bytes = int(capacity_bytes)
        self.entries = OrderedDict()
        self.live_bytes = self.peak_bytes = self.evictions = 0

    def __contains__(self, key):
        if key not in self.entries:
            return False
        self.entries.move_to_end(key)
        return True

    def add(self, key):
        size = int(key[-2]) * int(key[-1]) * 2
        if key in self.entries:
            self.entries.move_to_end(key)
            return
        if size > self.capacity_bytes:
            return  # legal streaming slot, not a retained tile
        while self.live_bytes + size > self.capacity_bytes:
            _, old = self.entries.popitem(last=False)
            self.live_bytes -= old
            self.evictions += 1
        self.entries[key] = size
        self.live_bytes += size
        self.peak_bytes = max(self.peak_bytes, self.live_bytes)


class MoEShape(Shape):
    def __init__(self, model, name, weight_base, workspace_base):
        super().__init__(model, name, False, weight_base, workspace_base)
        if weight_base is not None:
            # Finish all M rows for a compact N panel before proceeding to
            # another panel. Unlike M-major traversal + an unbounded set,
            # this permits actual B reuse without retaining the entire KxN.
            # NPUSim events, MACs, each output macro's K order, and tensor
            # addresses are unchanged. Only legal macro scheduling changes.
            self.plan = dict(self.plan)
            self.waves = sorted(self.waves, key=lambda w: (w['nj'], w['mi'], w['kk']))
            self.plan['waves'] = self.waves
            self.current_macro = (self.waves[0]['mi'], self.waves[0]['nj'])
            capacity = model.sram_capacity_bytes
            workspace = self.plan['resident_workspace_bytes']
            reserve = self.plan['output_hold_reserve_bytes']
            self.b_cache = CapacityBoundWeightCache(capacity - workspace - reserve)
            self.policy = dict(cache_group=f"resident:{name}", skip_b_dram=False)


class ProfileModel:
    def __init__(self):
        self.sc = json.loads((PARENT / "modeled_scenario.json").read_text())
        self.sram_capacity_bytes = json.loads((PREP / "native_hierarchy.json").read_text())["buffer_bytes"]
        self.plans = json.loads((PREP / "native_plan.json").read_text())
        for plan in self.plans.values():
            shift = plan["pipeline_cycles"]
            plan["waves"][0]["compute_cycles"] += shift
            for event in plan["waves"][0]["events"]:
                event[0] += shift
                event[1] += shift
        self.memory = MoEMemory(self.sc)
        self.streamable = {}


def run_part(part, model, cluster, opp_ratio=1.0):
    model.memory.available_ns[:] = 0
    model.memory.set_context(cluster, 1)
    now = 0.0
    counts = np.zeros(19)
    for _ in range(100000):
        if part.finished:
            break
        end, activity = part.advance(now, now + 1e12, opp_ratio, 1,
                                     lambda *event: None)
        if end <= now:
            raise RuntimeError("Native MoE profile made no progress")
        now = end
        counts += activity
    if not part.finished:
        raise RuntimeError("Native MoE profile did not finish")
    return now, counts


def profile_key(task, weight, workspace):
    return json.dumps((task["op"], task["read_bytes"], task["write_bytes"],
                       task["vector_ops"], task["reduce_ops"],
                       None if weight is None else weight % 8192,
                       workspace % 8192,
                       task["read_base"] % 8192,
                       task["write_base"] % 8192,
                       task.get("kv_native_role"),task.get("kv_head"),
                       task.get("kv_native_base_residue")), separators=(",", ":"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0,
                        help="diagnostic only; 0 profiles all unique tasks")
    args = parser.parse_args()
    manifest = json.loads((PREP / "manifest.json").read_text())
    sor_manifest = json.loads((PREP / "sor_manifest.json").read_text())
    capacity = json.loads((PREP / "capacity.json").read_text())
    addresses = json.loads((PREP / "tensor_addresses.json").read_text())
    place = json.loads((PREP / "placement.json").read_text())
    model = ProfileModel()
    profiles = {}
    task_keys = {"baseline": {}, "meta_sota": {}, "semantic_only": {}}
    for policy in ("baseline", "meta_sota", "semantic_only"):
        layout = "meta_sota" if policy == "semantic_only" else policy
        expert_place = (place["baseline_expert_cluster"] if policy == "baseline"
                        else place["meta_expert_cluster"])
        tasks = sor_manifest["tasks"] if policy == "meta_sota" else manifest["tasks"]
        for task in tasks:
            cluster = (expert_place[task["layer"]][task["expert"]]
                       if "expert" in task else task["primary_cluster"])
            workspace = capacity[layout][cluster]["scratch_base_address"]
            weight = (addresses[layout][task["weight_key"]]["base_address"]
                      if "weight_key" in task else None)
            prepared = copy.copy(task)
            if "kv_native_role" in task:
                head = task.get("kv_head", 0)
                kind = task["kv_native_role"][-1]
                prepared["kv_native_base_residue"] = addresses[layout][
                    f'l{task["layer"]}:kv:{kind}:h{head}']["base_address"] % 8192
                prepared["kv_native_address_book"] = addresses[layout]
            prepared["read_base"] = task_address(task, layout, addresses,
                                                capacity, cluster, "read")
            prepared["write_base"] = task_address(task, layout, addresses,
                                                 capacity, cluster, "write")
            key = profile_key(prepared, weight, workspace)
            task_keys[policy][str(task["task_id"])] = key
            if key in profiles:
                continue
            if args.limit and len(profiles) >= args.limit:
                continue
            generic = Generic(model, prepared, "shape" not in prepared)
            model.memory.current_task = None
            d0, a0 = run_part(generic, model, cluster)
            if "shape" in prepared:
                model.memory.current_task = prepared
                shape = MoEShape(model, prepared["shape"], weight, workspace)
                d1, a1 = run_part(shape, model, cluster)
                model.memory.current_task = None
            else:
                d1, a1 = 0., np.zeros(19)
            duration = d0 + d1
            activity = a0 + a1
            assert abs(activity[0] - task["mac_ops"]) < max(1., task["mac_ops"] * 1e-9)
            assert activity[5:13].min() >= 0 and activity[13:17].min() >= 0
            profiles[key] = dict(duration_ns=duration, activity=activity.tolist(),
                                 generic_ns=d0, shape_ns=d1)
            if len(profiles) % 100 == 0:
                print("PROFILED", len(profiles), flush=True)
    if args.limit:
        print(json.dumps(dict(status="DIAGNOSTIC_ONLY", unique_profiles=len(profiles))))
        return
    assert all(set(task_keys[policy].values()) <= set(profiles)
               for policy in task_keys)
    report = dict(status="NATIVE_PROFILE_PASS_BOUNDED_CONTEXT",
                  task_count_by_policy={"baseline": len(manifest["tasks"]),
                                        "meta_sota": len(sor_manifest["tasks"]),
                                        "semantic_only": len(manifest["tasks"])},
                  unique_profiles=len(profiles),
                  manifest_sha256={
                      "baseline": hashlib.sha256((PREP / "manifest.json").read_bytes()).hexdigest(),
                      "meta_sota": hashlib.sha256((PREP / "sor_manifest.json").read_bytes()).hexdigest(),
                      "semantic_only": hashlib.sha256((PREP / "manifest.json").read_bytes()).hexdigest()},
                  address_sha256=hashlib.sha256(
                      (PREP / "tensor_addresses.json").read_bytes()).hexdigest(),
                  capacity_sha256=hashlib.sha256(
                      (PREP / "capacity.json").read_bytes()).hexdigest(),
                  native_memory_profile_sha256=hashlib.sha256(
                      (PREP / "moe_logical_wave_profiles.json").read_bytes()).hexdigest(),
                  task_profile_keys=task_keys, profiles=profiles,
                  note="Task MAC and activity close. This is not a causal whole-graph run.")
    (PREP / "native_task_profiles.json").write_text(
        json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("task_profile_keys", "profiles")}, indent=2))


if __name__ == "__main__":
    main()

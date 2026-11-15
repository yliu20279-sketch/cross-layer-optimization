"""Re-profile each unique Qwen task at native 2/1.5/1 GHz NPU OPPs.

NPUSim cycle plans are replayed at 2.0/1.5/1.0 cycles per ns while the
existing Ramulator2/DRAMPower logical-wave profiles keep their own clocks.
The output is separate from the frozen 1-GHz experiment.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from build_native_profiles import (Generic, MoEShape, ProfileModel, profile_key,
                                  run_part, SRAM_RESIDENCY_POLICY)
from task_addresses import task_address

HERE = Path(__file__).resolve().parent
PREP = HERE / "prepared"
OP = PREP / "operating_point_2ghz_rconv3"
RATIOS = (1.0, 0.75, 0.5)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def setup(policy, scenario):
    meta = policy == "gtp_srs"
    manifest_file = PREP / ("gtp_srs_manifest.json" if meta else "manifest.json")
    address_file = PREP / ("gtp_srs_addresses.json" if meta else "tensor_addresses.json")
    capacity_file = PREP / ("gtp_srs_capacity.json" if meta else "capacity.json")
    memory_file = PREP / ("gtp_srs_logical_wave_profiles.json"
                          if meta else "moe_logical_wave_profiles.json")
    old_file = PREP / ("gtp_srs_native_task_profiles.json"
                       if meta else "native_task_profiles.json")
    manifest = read(manifest_file)
    addresses = {policy: read(address_file)} if meta else read(address_file)
    capacity = {policy: read(capacity_file)} if meta else read(capacity_file)
    old = read(old_file)
    placement = read(PREP / "placement.json")
    model = ProfileModel()
    model.sc = scenario
    model.memory.sc = scenario
    if meta:
        model.plans = read(PREP / "gtp_srs_native_plan.json")
        for plan in model.plans.values():
            shift = plan["pipeline_cycles"]
            plan["waves"][0]["compute_cycles"] += shift
            for event in plan["waves"][0]["events"]:
                event[0] += shift
                event[1] += shift
        model.memory.wave_profiles = read(memory_file)["profiles"]
    keys = old["task_profile_keys"] if meta else old["task_profile_keys"]["baseline"]
    return manifest, addresses, capacity, placement, model, keys, old_file, (
        manifest_file, address_file, capacity_file, memory_file)


def prepare_task(task, policy, addresses, capacity, placement):
    meta = policy == "gtp_srs"
    layout = "gtp_srs" if meta else "baseline"
    cluster = (placement["meta_expert_cluster" if meta else
                         "baseline_expert_cluster"][task["layer"]][task["expert"]]
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
    for side in ("read", "write"):
        prepared[f"{side}_base"] = task_address(
            task, layout, addresses, capacity, cluster, side)
    return prepared, cluster, workspace, weight


def profile_one(model, task, cluster, workspace, weight, opp):
    ratio_to_1ghz = 2.0 * opp
    generic = Generic(model, task, "shape" not in task)
    model.memory.current_task = None
    d0, a0 = run_part(generic, model, cluster, ratio_to_1ghz)
    if "shape" in task:
        model.memory.current_task = task
        shape = MoEShape(model, task["shape"], weight, workspace)
        d1, a1 = run_part(shape, model, cluster, ratio_to_1ghz)
        model.memory.current_task = None
    else:
        d1, a1 = 0.0, np.zeros(19)
    duration = d0 + d1
    a = a0 + a1
    p = model.sc["power"]
    peak = model.sc["activity_model"]["peak_fp16_MAC_per_cycle_per_cluster"]
    nominal = model.sc["activity_model"]["npu_frequency_Hz"]
    voltage = {1.0: 1.0, 0.75: 0.9, 0.5: 0.8}[opp]
    core_j = a[0] / (peak * nominal) * p["core_dynamic_full_W"] * voltage**2
    sram_j = (a[1] * p["sram_read_pJ_access"] +
              a[2] * p["sram_write_pJ_access"]) * 1e-12
    ns_to_s = duration * 1e-9
    assert duration > 0 and core_j >= 0 and sram_j >= 0
    return dict(duration_ns=duration, activity=a.tolist(),
                generic_ns=d0, shape_ns=d1,
                npu_opp_ratio=opp, npu_frequency_Hz=int(nominal*opp),
                native_compute_active_cycles=float(a[17]*ratio_to_1ghz),
                native_compute_active_ns=float(a[17]),
                native_DMA_occupied_ns=float(a[18]),
                compute_DMA_overlap_ns=max(0.0, float(a[17]+a[18]-duration)),
                compute_dynamic_energy_J=float(core_j),
                SRAM_dynamic_energy_J=float(sram_j),
                mean_compute_dynamic_W=float(core_j/ns_to_s),
                mean_SRAM_dynamic_W=float(sram_j/ns_to_s),
                sram_residency_policy=SRAM_RESIDENCY_POLICY,
                peak_retained_weight_bytes=(shape.b_cache.peak_bytes if
                    'shape' in task and weight is not None else 0),
                reserved_workspace_bytes=(shape.plan['resident_workspace_bytes']+
                    shape.plan['output_hold_reserve_bytes'] if 'shape' in task else 0),
                physical_SRAM_bytes=model.sram_capacity_bytes)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", choices=("baseline", "gtp_srs"), required=True)
    parser.add_argument("--limit", type=int, default=0,
                        help="diagnostic only: first N unique profile keys")
    parser.add_argument("--reuse-unaffected-from", type=Path,
                        help="Reuse only profiles whose task waveform is provably unchanged")
    args = parser.parse_args()
    scenario_path = OP / "scenario.json"
    sc = read(scenario_path)
    assert sc["activity_model"]["npu_frequency_Hz"] == 2_000_000_000
    assert sc["timing"]["noc_cycle_ns"] == 1
    assert sc["timing"]["dram_clock_period_ns"] == 1.25
    manifest, addresses, capacity, placement, model, keys, old_file, sources = (
        setup(args.policy, sc))
    output = {str(opp): {} for opp in RATIOS}
    prior = read(args.reuse_unaffected_from) if args.reuse_unaffected_from else None
    if prior:
        assert prior['scenario_sha256'] == sha(scenario_path)
        assert prior['source_profile_sha256'] == sha(old_file)
        assert prior['task_profile_keys'] == keys
        assert prior['source_file_sha256'] == {p.name: sha(p) for p in sources}
    reused = reprofiling = 0
    seen = set()
    for task in manifest["tasks"]:
        key = keys[str(task["task_id"])]
        if key in seen:
            continue
        if args.limit and len(seen) >= args.limit:
            break
        prepared, cluster, workspace, weight = prepare_task(
            task, args.policy, addresses, capacity, placement)
        assert profile_key(prepared, weight, workspace) == key
        seen.add(key)
        triplet = {}
        unchanged = weight is None or len({w['mi'] for w in model.plans[task['shape']]['waves']}) == 1
        for opp in RATIOS:
            if prior and unchanged:
                # Nonweight Shape traversal is unchanged; single-M weight
                # tasks have no B cache hits, so eviction cannot change DMA.
                entry = dict(prior['profiles'][str(opp)][key])
                entry['sram_residency_policy'] = SRAM_RESIDENCY_POLICY
                entry['reuse_reason'] = 'NO_WEIGHT_OR_SINGLE_M_NO_REUSE_WAVEFORM_UNCHANGED'
            else:
                entry = profile_one(model, prepared, cluster, workspace, weight, opp)
            a = np.asarray(entry["activity"])
            assert abs(a[0]-task["mac_ops"]) < max(1.,task["mac_ops"]*1e-9)
            triplet[opp] = entry
            output[str(opp)][key] = entry
        reused += bool(prior and unchanged)
        reprofiling += not bool(prior and unchanged)
        assert (triplet[1.0]["duration_ns"] <=
                triplet[0.75]["duration_ns"]+1e-5 <=
                triplet[0.5]["duration_ns"]+2e-5)
        for opp in (0.75,0.5):
            np.testing.assert_allclose(
                triplet[1.0]["activity"][:17],
                triplet[opp]["activity"][:17], rtol=1e-9, atol=1e-7)
        if len(seen) % 100 == 0:
            print("NATIVE_OPP_PROFILED", args.policy, len(seen), flush=True)
    if not args.limit:
        assert seen == set(keys.values())
    report = dict(status=("DIAGNOSTIC_ONLY" if args.limit else
                          "NATIVE_2GHZ_THREE_OPP_PASS_BOUNDED_DRAM"),
                  policy=args.policy, task_count=len(manifest["tasks"]),
                  unique_profiles=len(seen), source_profile_sha256=sha(old_file),
                  source_file_sha256={p.name: sha(p) for p in sources},
                  scenario_sha256=sha(scenario_path),
                  thermal_rc_A_sha256=sha(OP/"rc/A.csv"),
                  opp_frequency_Hz={str(x):int(2e9*x) for x in RATIOS},
                  opp_voltage_ratio={"1.0":1.0,"0.75":0.9,"0.5":0.8},
                  task_profile_keys=keys, profiles=output,
                  memory_scope="BOUNDED_PER_TASK; no global command-state claim")
    report.update(sram_residency_policy=SRAM_RESIDENCY_POLICY,
                  residency_implementation_sha256=sha(HERE/'build_native_profiles.py'),
                  hierarchy_sha256=sha(PREP/'native_hierarchy.json'),
                  reused_waveform_equivalent_profiles=reused,
                  regenerated_native_three_OPP_profiles=reprofiling,
                  prior_profile_sha256=sha(args.reuse_unaffected_from) if prior else None)
    label = "_diagnostic" if args.limit else ""
    destination = OP / f"{args.policy}_native_opp_profiles{label}.json"
    destination.write_text(json.dumps(report, separators=(",",":"))+"\n")
    print(json.dumps({k:v for k,v in report.items()
                      if k not in ("task_profile_keys","profiles")}, indent=2))


if __name__ == "__main__":
    main()

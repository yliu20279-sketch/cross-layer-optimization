#!/usr/bin/env python3
"""Frozen representative-layer pressure screen using real Qwen routes.

Arrivals are simultaneous and therefore explicitly synthetic stress, while
route cohorts and all memory transactions come from the captured workloads.
"""
import concurrent.futures
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
SUITE = ROOT / "results/bank_pressure_screen_v1"
BINARY = ROOT / "toolchain/popnet_cross_request_release_v2/build_eventjump_v6/popnet"
RAMULATOR = ROOT / "toolchain/ramulator2_cross_request_v1/libramulator.so"
CONTEXTS = (128, 512)
BATCHES = (8, 16)
POLICIES = ("exploratory_low_skew", "exploratory_high_skew")
LAYERS = (0, 25, 47)


def env():
    e = os.environ.copy()
    e["PYTHONPATH"] = str(ROOT) + os.pathsep + e.get("PYTHONPATH", "")
    e["HB_BANK_LOG_DETAIL"] = "0"
    return e


def release_file(batch):
    path = SUITE / "releases" / f"simultaneous_c{batch}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", newline="") as h:
            w = csv.DictWriter(h, fieldnames=("owner", "release_cycle"))
            w.writeheader()
            for owner in range(batch):
                w.writerow({"owner": owner, "release_cycle": 0})
    return path


def case_name(ctx, batch, policy, layer):
    skew = "low" if policy.endswith("low_skew") else "high"
    return f"ctx{ctx}_c{batch}_{skew}_L{layer}"


def prepare_graph(ctx, batch, policy, layer):
    name = case_name(ctx, batch, policy, layer)
    graph = SUITE / "graphs" / name
    manifest = graph / "graph_manifest.json"
    if manifest.exists():
        return graph
    command = [sys.executable, HERE / "build_arrival_sampling_graph.py",
        "--root", ROOT, "--context", ctx, "--batch", batch, "--steps", 1,
        "--layer-start", layer, "--layers", 1, "--microbatch-size", 1,
        "--partition-capacity-mib", 512, "--cohort-policy", policy,
        "--cohort-repeat", 1,
        "--placement", ROOT / f"results/sem_moe_reproduction_ctx{ctx}_v2/placement.json",
        "--compute-profile", ROOT / "scalesim_compute_profile_v1.json",
        "--hiband", "--full-memory-trace", "--out", graph]
    subprocess.run(list(map(str, command)), cwd=ROOT, env=env(), check=True,
                   stdout=subprocess.DEVNULL)
    return graph


def run_one(job):
    ctx, batch, policy, layer, mode = job
    name = case_name(ctx, batch, policy, layer)
    graph = prepare_graph(ctx, batch, policy, layer)
    out = SUITE / "runs" / f"{name}_{mode}"
    validation = out / "validation.json"
    if validation.exists() and json.loads(validation.read_text()).get("status") == "PASS":
        return {"case": name, "mode": mode, "status": "SKIP_PASS"}
    command = [sys.executable, HERE / "run_arrival_sampling.py", "--root", ROOT,
        "--graph", graph, "--out", out, "--binary", BINARY,
        "--ramulator-library", RAMULATOR, "--request-releases", release_file(batch),
        "--hiband", "--timeout-seconds", 1800]
    if mode == "oracle":
        command.append("--ignore-cross-request-bank-timing")
    logs = SUITE / "launcher_logs"; logs.mkdir(parents=True, exist_ok=True)
    with (logs / f"{name}_{mode}.log").open("w") as h:
        result = subprocess.run(list(map(str, command)), cwd=ROOT, env=env(),
                                stdout=h, stderr=subprocess.STDOUT)
    return {"case": name, "mode": mode,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "returncode": result.returncode}


def analyze():
    rows = []
    for ctx in CONTEXTS:
        for batch in BATCHES:
            for policy in POLICIES:
                for layer in LAYERS:
                    name = case_name(ctx, batch, policy, layer)
                    n = json.loads((SUITE / "runs" / f"{name}_normal/validation.json").read_text())
                    o = json.loads((SUITE / "runs" / f"{name}_oracle/validation.json").read_text())
                    delta = n["total_cycles"] - o["total_cycles"]
                    rows.append({"case": name, "context": ctx, "concurrency": batch,
                        "route_policy": policy, "layer": layer,
                        "normal_cycles": n["total_cycles"], "oracle_cycles": o["total_cycles"],
                        "exposed_bank_cycles": delta,
                        "exposed_fraction": delta / n["total_cycles"],
                        "advance_to_full48": delta / n["total_cycles"] >= 0.01})
    with (SUITE / "screen_results.csv").open("w", newline="") as h:
        w = csv.DictWriter(h, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    report = {"status": "PASS", "threshold": 0.01,
              "natural_component": "captured Qwen3 routing cohorts",
              "synthetic_stress_component": "all requests released at cycle zero",
              "cases": len(rows), "advanced": [r for r in rows if r["advance_to_full48"]],
              "best": sorted(rows, key=lambda r: r["exposed_fraction"], reverse=True)[:8]}
    (SUITE / "screen_report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    SUITE.mkdir(parents=True, exist_ok=True)
    freeze = {"contexts": CONTEXTS, "concurrency": BATCHES,
              "route_policies": POLICIES, "layers": LAYERS,
              "arrival": "simultaneous synthetic stress", "full_memory_trace": True,
              "partition_capacity_mib": 512, "max_workers": 2,
              "promotion_threshold_exposed_fraction": 0.01}
    (SUITE / "frozen_design.json").write_text(json.dumps(freeze, indent=2) + "\n")
    for c in CONTEXTS:
        for b in BATCHES:
            for p in POLICIES:
                for l in LAYERS:
                    prepare_graph(c, b, p, l)
    jobs = [(c, b, p, l, m) for c in CONTEXTS for b in BATCHES
            for p in POLICIES for l in LAYERS for m in ("normal", "oracle")]
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for result in pool.map(run_one, jobs):
            print(json.dumps(result), flush=True); results.append(result)
    (SUITE / "launcher_status.json").write_text(json.dumps(results, indent=2) + "\n")
    if any(r["status"] == "FAIL" for r in results):
        raise SystemExit(1)
    print(json.dumps(analyze(), indent=2))


if __name__ == "__main__":
    main()

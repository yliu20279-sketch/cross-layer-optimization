#!/usr/bin/env python3
"""Independent repeat-3 profile / repeat-4 held-out soft70 diagnostic.

Run on the original server. All writes stay under results/coaccess_transfer_v2.
Existing tools, source traces, and PASS results are read-only.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path("/mnt/sda1/h3240101068/qwen3_30b_a3b_v3_6_experiment")
OLD = ROOT / "results/expert_page_layout_v1"
OUT = ROOT / "results/coaccess_transfer_v2"
PLACEMENT = ROOT / "results/sem_moe_reproduction_ctx512_v2/placement.json"
COMPUTE = ROOT / "scalesim_compute_profile_v1.json"
ASSIGNMENT = OLD / "layouts/full48_round_robin_assignment.csv"
BINARY = OLD / "toolchain/popnet_layout/build_page/popnet"
RAM = OLD / "toolchain/ramulator2_layout/libramulator.so"
RELEASES = ROOT / "results/bank_memory_stress_full48_co_scale_strict_v2/releases/simultaneous_c4.csv"


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call(stage: str, command: list[str]):
    print(json.dumps({"stage": stage, "command": command}), flush=True)
    begun = time.time()
    completed = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
    log = OUT / f"{stage}.log"
    log.write_text(completed.stdout)
    record = {"stage": stage, "returncode": completed.returncode,
              "wall_seconds": time.time() - begun, "log": str(log)}
    (OUT / f"{stage}.status.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record), flush=True)
    if completed.returncode:
        raise RuntimeError(f"{stage} failed; original log retained at {log}")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / "results/route_characterization/cohort_manifest.json").read_text())
    cohorts = {r: next(c["request_ids"] for c in manifest["cohorts"]
                       if c["policy"] == "exploratory_low_skew" and
                       c["repeat"] == r and c["scale"] == 4)
               for r in (1, 2, 3, 4)}
    if set(cohorts[3]) & set(cohorts[4]) or set(cohorts[3] + cohorts[4]) & set(cohorts[1] + cohorts[2]):
        raise ValueError("new profile/evaluation requests overlap each other or old pair")
    inputs = {"profile_repeat": 3, "evaluation_repeat": 4,
              "cohorts": cohorts, "placement_sha256": sha(PLACEMENT),
              "compute_sha256": sha(COMPUTE), "assignment_sha256": sha(ASSIGNMENT),
              "binary_sha256": sha(BINARY), "ramulator_sha256": sha(RAM)}
    (OUT / "frozen_inputs.json").write_text(json.dumps(inputs, indent=2) + "\n")
    for role, repeat in (("profile", 3), ("evaluation", 4)):
        source = OUT / f"graphs/{role}_source"
        stressed = OUT / f"graphs/{role}_soft70"
        transactions = OUT / f"layouts/{role}_round_robin_transactions.csv"
        run = OUT / f"runs/{role}_soft70_round_robin"
        call(f"{role}_build", [sys.executable, str(OLD / "build_bank_aware_graph.py"),
             "--root", str(ROOT), "--context", "512", "--batch", "4", "--steps", "1",
             "--microbatch-size", "1", "--full-memory-trace",
             "--cohort-policy", "exploratory_low_skew", "--cohort-repeat", str(repeat),
             "--placement", str(PLACEMENT), "--page-bank-map", str(ASSIGNMENT),
             "--compute-profile", str(COMPUTE), "--hiband", "--out", str(source)])
        call(f"{role}_stress", [sys.executable,
             str(ROOT / "bank_conflict_v2/build_qwen3_memory_stress.py"),
             "--input", str(source), "--output", str(stressed),
             "--lanes", "0", "--compute-multiplier", "0.25"])
        call(f"{role}_mapping", [sys.executable, str(OLD / "build_graph_page_map.py"),
             "--graph", str(stressed), "--placement", str(PLACEMENT),
             "--assignment", str(ASSIGNMENT), "--out", str(transactions)])
        call(f"{role}_run", [sys.executable, str(OLD / "run_layout_sampling.py"),
             "--root", str(OLD), "--graph", str(stressed), "--out", str(run),
             "--binary", str(BINARY), "--ramulator-library", str(RAM),
             "--request-releases", str(RELEASES), "--hiband",
             "--max-outstanding-per-op", "1", "--bank-address-mode", "soft_hot",
             "--effective-banks", "16", "--soft-hot-percent", "70",
             "--bank-field-shift", "14", "--timeout-seconds", "86400"])
        validation = json.loads((run / "validation.json").read_text())
        if validation["status"] != "PASS":
            raise RuntimeError(f"{role} validation not PASS")
        graph = json.loads((stressed / "graph_manifest.json").read_text())
        if graph["request_ids"] != cohorts[repeat]:
            raise RuntimeError(f"{role} request IDs mismatch")
    (OUT / "PAIR34_READY").write_text("profile and evaluation PASS\n")
    print("PAIR34_READY", flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Evaluate pair 3->4 after both diagnostic runs have passed."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path("/mnt/sda1/h3240101068/qwen3_30b_a3b_v3_6_experiment")
OLD = ROOT / "results/expert_page_layout_v1"
SUITE = ROOT / "results/coaccess_transfer_v2"
HERE = SUITE


def run(name, command):
    done = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    (SUITE / f"{name}.log").write_text(done.stdout)
    if done.returncode:
        raise RuntimeError(f"{name} failed with {done.returncode}; log retained")


def main():
    if not (SUITE / "PAIR34_READY").is_file():
        raise RuntimeError("pair 3->4 simulations have not both passed")
    profile = SUITE / "runs/profile_soft70_round_robin/events.csv"
    evaluation = SUITE / "runs/evaluation_soft70_round_robin/events.csv"
    heat = SUITE / "layouts/profile3_heat.csv"
    coaccess = SUITE / "layouts/profile3_coaccess.csv"
    for p in (profile, evaluation):
        if not p.is_file():
            raise FileNotFoundError(p)
    run("derive", [sys.executable, str(OLD / "derive_profile_assignments.py"),
        "--placement", str(ROOT / "results/sem_moe_reproduction_ctx512_v2/placement.json"),
        "--profile-events", str(profile), "--cache-slots-per-partition", "187",
        "--out-heat", str(heat), "--out-coaccess", str(coaccess),
        "--out-summary", str(SUITE / "assignment_summary.json")])
    run("fixed_trace", [sys.executable, str(HERE / "validate_coaccess_fixed_trace.py"),
        "--profile-events", str(profile), "--evaluation-events", str(evaluation),
        "--trace-label", "independent_repeat4_round_robin",
        "--heat-layout", str(heat), "--coaccess-layout", str(coaccess),
        "--round-robin-layout", str(OLD / "layouts/full48_round_robin_assignment.csv"),
        "--output", str(SUITE / "fixed_trace_pair34.json")])
    metrics = json.loads((SUITE / "fixed_trace_pair34.json").read_text())
    coverage = metrics["profile_to_evaluation_edge_coverage"]["evaluation_overlap_weight_fraction"]
    scores = metrics["heldout_fixed_timeline_scores"]
    heat_score = scores["heat"]["same_bank_overlap"]
    co_score = scores["coaccess"]["same_bank_overlap"]
    round_robin_score = scores["round_robin"]["same_bank_overlap"]
    screen = {
        "status": "PASS_SCREEN" if coverage >= 0.10 and co_score < heat_score else "NO_PROMOTION",
        "meaning": "One independent profile/evaluation pair; not a multi-seed confidence interval",
        "coverage_threshold_predeclared": 0.10,
        "coverage_weight_fraction": coverage,
        "heat_same_bank_overlap": heat_score,
        "coaccess_same_bank_overlap": co_score,
        "round_robin_same_bank_overlap": round_robin_score,
        "coaccess_improvement_over_heat": heat_score - co_score,
        "coaccess_improvement_over_round_robin": round_robin_score - co_score,
        "next_step": "If PASS_SCREEN, inspect another independent pair and equal-change null before full48; otherwise stop at mechanism screen",
    }
    (SUITE / "screen_pair34.json").write_text(json.dumps(screen, indent=2) + "\n")
    print(json.dumps(screen, indent=2))


if __name__ == "__main__":
    main()

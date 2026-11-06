#!/usr/bin/env python3
"""Run c1/c2 for the c4-selected Bank-alias pressure and balanced control."""
import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
SOURCE = ROOT / "results/bank_memory_stress_full48_co_scale_strict_v2"
SCREEN = ROOT / "results/bank_alias_pressure_screen_c4_v2"
SUITE = ROOT / "results/bank_alias_pressure_selected_scale_v1"
BINARY = ROOT / "toolchain/popnet_cross_request_release_v2/build_bank_alias_v1/popnet"
RAM = ROOT / "toolchain/ramulator2_cross_request_v1/libramulator.so"


def run_one(job):
    concurrency, label, mapping, banks, mode = job
    out = SUITE / "runs" / f"c{concurrency}_{label}_{mode}"
    cmd = [
        sys.executable, HERE / "run_arrival_sampling.py",
        "--root", ROOT,
        "--graph", SOURCE / "graphs" / f"c{concurrency}_co",
        "--out", out,
        "--binary", BINARY,
        "--ramulator-library", RAM,
        "--request-releases", SOURCE / "releases" / f"simultaneous_c{concurrency}.csv",
        "--hiband", "--max-outstanding-per-op", "1",
        "--bank-address-mode", mapping, "--effective-banks", str(banks),
        "--bank-field-shift", "14", "--timeout-seconds", "14400",
    ]
    if mode == "oracle":
        cmd.append("--ignore-cross-request-bank-timing")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["HB_BANK_LOG_DETAIL"] = "0"
    logs = SUITE / "launcher_logs"
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / f"c{concurrency}_{label}_{mode}.log").open("w") as handle:
        result = subprocess.run([str(x) for x in cmd], cwd=ROOT, env=env,
                                stdout=handle, stderr=subprocess.STDOUT)
    return {"concurrency": concurrency, "case": label, "mapping": mapping,
            "effective_banks": banks, "mode": mode,
            "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 else "FAIL"}


def main():
    screen = json.loads((SCREEN / "screen_report.json").read_text())
    winner = screen["winner"]
    banks = int(winner["effective_banks"])
    SUITE.mkdir(parents=True, exist_ok=True)
    design = {
        "status": "FROZEN",
        "classification": "controlled address-mapping stress; not a natural Qwen3 workload",
        "selection_source": str((SCREEN / "screen_report.json").relative_to(ROOT)),
        "selection_rule": screen["selection_rule"],
        "selected_alias_case": winner["case"],
        "selected_effective_banks": banks,
        "concurrencies": [1, 2, 4],
        "c4_evidence": "reused from the frozen screening suite; c1/c2 are run here",
        "paired_cases": ["selected alias normal/oracle", "balanced16 normal/oracle"],
        "invariants": ["full 48-layer C+O DAG", "context 512", "compute multiplier 0.25",
                       "outstanding=1", "simultaneous arrivals", "unchanged transaction stream"],
    }
    (SUITE / "frozen_design.json").write_text(json.dumps(design, indent=2) + "\n")
    jobs = []
    for concurrency in (1, 2):
        for label, mapping, count in ((winner["case"], "alias", banks),
                                      ("balanced16", "balanced", 16)):
            for mode in ("normal", "oracle"):
                jobs.append((concurrency, label, mapping, count, mode))
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        status = list(pool.map(run_one, jobs))
    (SUITE / "launcher_status.json").write_text(json.dumps(status, indent=2) + "\n")
    if any(row["returncode"] for row in status):
        raise SystemExit(1)
    print(json.dumps({"status": "PASS", "runs": len(status), "winner": winner["case"]}, indent=2))


if __name__ == "__main__":
    main()

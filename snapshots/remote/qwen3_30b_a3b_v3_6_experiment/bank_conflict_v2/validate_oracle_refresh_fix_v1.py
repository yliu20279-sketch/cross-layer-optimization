#!/usr/bin/env python3
"""Sequential c1 null test for the cross-request Bank oracle."""
import csv
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "results/bank_memory_stress_full48_co_scale_v1"
GRAPH = SUITE / "graphs/c1_co"
BINARY = ROOT / "toolchain/popnet_cross_request_release_v2/build_outstanding_v7/popnet"
RAM = ROOT / "toolchain/ramulator2_cross_request_v1/libramulator.so"
RELEASES = SUITE / "releases/simultaneous_c1.csv"


def aggregate(path):
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {
        "transactions": sum(int(row["transactions"]) for row in rows),
        "waited_transactions": sum(int(row["transactions_with_cross_request_wait"]) for row in rows),
        "cross_request_wait_ticks": sum(int(row["cross_request_bank_wait_ticks"]) for row in rows),
    }


def main():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["HB_BANK_LOG_DETAIL"] = "0"
    test_root = SUITE / "oracle_refresh_fix_test"
    test_root.mkdir(parents=True, exist_ok=True)
    results = {}
    for mode in ("normal", "oracle"):
        out = test_root / mode
        cmd = [
            sys.executable, ROOT / "bank_conflict_v2/run_arrival_sampling.py",
            "--root", ROOT, "--graph", GRAPH, "--out", out,
            "--binary", BINARY, "--ramulator-library", RAM,
            "--request-releases", RELEASES, "--hiband",
            "--max-outstanding-per-op", "1", "--timeout-seconds", "14400",
        ]
        if mode == "oracle":
            cmd.append("--ignore-cross-request-bank-timing")
        with (test_root / f"{mode}.log").open("w") as log:
            subprocess.run([str(x) for x in cmd], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        validation = json.loads((out / "validation.json").read_text())
        results[mode] = {"total_cycles": validation["total_cycles"], **aggregate(out / "bank_aggregate.csv")}
    passed = (
        results["normal"]["total_cycles"] == results["oracle"]["total_cycles"]
        and results["normal"]["transactions"] == results["oracle"]["transactions"]
        and results["normal"]["waited_transactions"] == 0
        and results["normal"]["cross_request_wait_ticks"] == 0
    )
    report = {
        "status": "PASS" if passed else "FAIL",
        "test": "c1 null test: normal and cross-request-Bank oracle must be identical",
        "ramulator_sha256": hashlib.sha256(RAM.read_bytes()).hexdigest(),
        "results": results,
    }
    (test_root / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

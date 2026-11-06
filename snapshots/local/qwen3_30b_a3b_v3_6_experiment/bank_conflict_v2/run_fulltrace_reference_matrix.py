#!/usr/bin/env python3
import concurrent.futures
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
SUITE = ROOT / "results/bank_sampling_fulltrace_reference_v1"
BINARY = ROOT / "toolchain/popnet_cross_request_release_v2/build_release_v2/popnet"
RAMULATOR = ROOT / "toolchain/ramulator2_cross_request_v1/libramulator.so"
LABELS = ["s4096", "s16384", "s65536", "s262144", "s1048576", "full"]


def one(item):
    batch, label = item
    graph = SUITE / "graphs" / f"ctx128_c{batch}_l1_t1_{label}"
    out = SUITE / "runs" / f"ctx128_c{batch}_l1_t1_{label}_normal"
    validation = out / "validation.json"
    if validation.exists() and json.loads(validation.read_text()).get("status") == "PASS":
        return {"batch": batch, "label": label, "status": "SKIP_PASS"}
    command = [
        sys.executable, HERE / "run_arrival_sampling.py",
        "--root", ROOT, "--graph", graph, "--out", out,
        "--binary", BINARY, "--ramulator-library", RAMULATOR,
        "--request-releases", SUITE / f"c{batch}_simultaneous_release.csv",
        "--hiband", "--timeout-seconds", 3600,
    ]
    logs = SUITE / "launcher_logs"
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / f"c{batch}_{label}.log").open("w") as handle:
        result = subprocess.run(list(map(str, command)), stdout=handle, stderr=subprocess.STDOUT)
    return {"batch": batch, "label": label, "status": "PASS" if result.returncode == 0 else "FAIL", "returncode": result.returncode}


def main():
    jobs = [(batch, label) for batch in (2, 8) for label in LABELS]
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for result in pool.map(one, jobs):
            print(json.dumps(result), flush=True)
            results.append(result)
    (SUITE / "launcher_status.json").write_text(json.dumps(results, indent=2) + "\n")
    if any(row["status"] == "FAIL" for row in results):raise SystemExit(1)


if __name__ == "__main__":main()

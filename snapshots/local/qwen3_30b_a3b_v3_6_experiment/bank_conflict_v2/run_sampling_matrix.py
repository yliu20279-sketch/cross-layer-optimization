#!/usr/bin/env python3
import concurrent.futures
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
SUITE = ROOT / "results/bank_conflict_arrival_sampling_v2"
BINARY = ROOT / "toolchain/popnet_cross_request_release_v2/build_release_v2/popnet"
RAMULATOR = ROOT / "toolchain/ramulator2_cross_request_v1/libramulator.so"
LEVELS = [2048, 4096, 8192, 16384, 32768]


def command(batch, sample):
    mode = "finite_overlap" if batch == 2 else "bursty"
    graph_mode = "steady" if batch == 2 else "bursty"
    release = (
        HERE / "c2_finite_overlap_releases.csv"
        if batch == 2 else SUITE / "releases/bursty_c8_seed1101.csv"
    )
    graph = SUITE / "graphs" / f"ctx128_c{batch}_{graph_mode}_s{sample}"
    out = SUITE / "runs" / f"ctx128_c{batch}_{mode}_s{sample}_normal"
    return out, [
        sys.executable, HERE / "run_arrival_sampling.py",
        "--root", ROOT, "--graph", graph, "--out", out,
        "--binary", BINARY, "--ramulator-library", RAMULATOR,
        "--request-releases", release, "--hiband", "--timeout-seconds", 3600,
    ]


def one(item):
    batch, sample = item
    out, cmd = command(batch, sample)
    validation = out / "validation.json"
    if validation.exists() and json.loads(validation.read_text()).get("status") == "PASS":
        return {"batch": batch, "sample": sample, "status": "SKIP_PASS"}
    log = SUITE / "launcher_logs" / f"c{batch}_s{sample}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as handle:
        proc = subprocess.run(list(map(str, cmd)), stdout=handle, stderr=subprocess.STDOUT)
    return {"batch": batch, "sample": sample, "status": "PASS" if proc.returncode == 0 else "FAIL", "returncode": proc.returncode}


def main():
    jobs = [(b, s) for b in (2, 8) for s in LEVELS]
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for result in pool.map(one, jobs):
            print(json.dumps(result), flush=True)
            results.append(result)
    (SUITE / "sampling_launcher_status.json").write_text(json.dumps(results, indent=2) + "\n")
    if any(x["status"] == "FAIL" for x in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

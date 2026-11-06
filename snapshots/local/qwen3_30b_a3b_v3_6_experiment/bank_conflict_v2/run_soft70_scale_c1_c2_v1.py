#!/usr/bin/env python3
"""Complete the c1/c2 strict normal-oracle pairs for the selected soft70 stress."""
import concurrent.futures, hashlib, json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
SOURCE = ROOT / "results/bank_memory_stress_full48_co_scale_strict_v2"
SUITE = ROOT / "results/bank_soft70_scale_v1"
BINARY = ROOT / "toolchain/popnet_cross_request_release_v2/build_layer_heatmap_v1/popnet"
RAM = ROOT / "toolchain/ramulator2_cross_request_v1/libramulator_soft_hot_v1.so"
CONCURRENCIES = (1, 2)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(job):
    concurrency, mode = job
    graph = SOURCE / "graphs" / f"c{concurrency}_co"
    releases = SOURCE / "releases" / f"simultaneous_c{concurrency}.csv"
    out = SUITE / "runs" / f"c{concurrency}_soft70_{mode}"
    cmd = [sys.executable, HERE / "run_arrival_sampling.py",
           "--root", ROOT, "--graph", graph, "--out", out,
           "--binary", BINARY, "--ramulator-library", RAM,
           "--request-releases", releases, "--hiband",
           "--max-outstanding-per-op", "1", "--bank-address-mode", "soft_hot",
           "--effective-banks", "16", "--soft-hot-percent", "70",
           "--bank-field-shift", "14", "--timeout-seconds", "43200"]
    if mode == "oracle":
        cmd.append("--ignore-cross-request-bank-timing")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["HB_BANK_LOG_DETAIL"] = "0"
    logs = SUITE / "launcher_logs"
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / f"c{concurrency}_{mode}.log").open("w") as handle:
        rc = subprocess.run([str(x) for x in cmd], cwd=ROOT, env=env,
                            stdout=handle, stderr=subprocess.STDOUT).returncode
    return {"concurrency": concurrency, "mode": mode,
            "returncode": rc, "status": "PASS" if rc == 0 else "FAIL"}

def main():
    SUITE.mkdir(parents=True, exist_ok=True)
    design = {
        "status": "FROZEN",
        "classification": "controlled soft70 Bank-hotspot address-mapping stress; not a natural Qwen3 workload",
        "model": "Qwen3-30B-A3B", "layers": 48, "context": 512,
        "concurrencies": list(CONCURRENCIES), "compute_multiplier": 0.25,
        "max_outstanding_per_memory_op": 1, "arrival": "simultaneous",
        "global_bank_coverage_requirement": "all decoded Bank IDs 0-15 nonzero",
        "partition_coverage_requirement": "all 16 partitions nonzero",
        "paired_oracle": "only cross-request same-Bank timing blockers removed",
        "binary_sha256": sha(BINARY), "ramulator_sha256": sha(RAM),
        "limitations": ["single deterministic captured cohort (n=1)", "address-mapping stress"]}
    (SUITE / "frozen_design.json").write_text(json.dumps(design, indent=2) + "\n")
    jobs = [(c, m) for c in CONCURRENCIES for m in ("normal", "oracle")]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        status = list(pool.map(run, jobs))
    (SUITE / "launcher_status.json").write_text(json.dumps(status, indent=2) + "\n")
    if any(x["returncode"] for x in status):
        raise SystemExit(1)
    print(json.dumps({"status": "PASS", "runs": len(status)}, indent=2))

if __name__ == "__main__":
    main()

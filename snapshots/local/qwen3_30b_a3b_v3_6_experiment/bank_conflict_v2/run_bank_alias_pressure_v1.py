#!/usr/bin/env python3
"""Full-48-layer c16 C+O address-mapping stress matrix."""
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
SOURCE = ROOT / "results/bank_memory_stress_full48_co_scale_strict_v2"
SUITE = ROOT / "results/bank_alias_pressure_screen_c4_v2"
GRAPH = SOURCE / "graphs/c4_co"
RELEASES = SOURCE / "releases/simultaneous_c4.csv"
BINARY = ROOT / "toolchain/popnet_cross_request_release_v2/build_bank_alias_v1/popnet"
RAM = ROOT / "toolchain/ramulator2_cross_request_v1/libramulator.so"
CASES = (
    ("balanced16", "balanced", 16),
    ("effective16", "alias", 16),
    ("effective8", "alias", 8),
    ("effective4", "alias", 4),
    ("effective2", "alias", 2),
)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_one(job):
    name, mapping, banks, mode = job
    out = SUITE / "runs" / f"{name}_{mode}"
    validation = out / "validation.json"
    if validation.exists() and json.loads(validation.read_text()).get("status") == "PASS":
        return {"case": name, "mapping": mapping, "effective_banks": banks,
                "mode": mode, "returncode": 0, "status": "PASS_REUSED"}
    cmd = [
        sys.executable, HERE / "run_arrival_sampling.py",
        "--root", ROOT, "--graph", GRAPH, "--out", out,
        "--binary", BINARY, "--ramulator-library", RAM,
        "--request-releases", RELEASES, "--hiband",
        "--max-outstanding-per-op", "1",
        "--bank-address-mode", mapping, "--effective-banks", str(banks),
        "--bank-field-shift", "14", "--timeout-seconds", "43200",
    ]
    if mode == "oracle":
        cmd.append("--ignore-cross-request-bank-timing")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["HB_BANK_LOG_DETAIL"] = "0"
    logs = SUITE / "launcher_logs"
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / f"{name}_{mode}.log").open("w") as handle:
        result = subprocess.run([str(x) for x in cmd], cwd=ROOT, env=env,
                                stdout=handle, stderr=subprocess.STDOUT)
    return {"case": name, "mapping": mapping, "effective_banks": banks,
            "mode": mode, "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 else "FAIL"}


def main():
    SUITE.mkdir(parents=True, exist_ok=True)
    design = {
        "status": "FROZEN",
        "classification": "controlled address-mapping stress; not a natural Qwen3 workload",
        "model": "Qwen3-30B-A3B",
        "graph": str(GRAPH.relative_to(ROOT)),
        "layers": 48,
        "context": 512,
        "concurrency": 4,
        "compute_multiplier": 0.25,
        "max_outstanding_per_memory_op": 1,
        "arrival": "simultaneous",
        "mapping_cases": [{"name": n, "mode": m, "effective_banks": b} for n, m, b in CASES],
        "bank_field": {"byte_address_bits": [14, 17], "decode": "bankgroup*4+bank"},
        "alias_transform": "after frontend acceptance, mapped_bank = original_decoded_bank mod effective_banks; original physical address plus row and column decoding remain unchanged",
        "balanced_transform": "after frontend acceptance, mapped_bank = splitmix64(original physical address || request owner) mod 16; original physical address plus row and column decoding remain unchanged",
        "paired_oracle": "only cross-request same-Bank timing blockers removed; global row state preserved",
        "invariants": ["same DAG", "same routes and placement", "same request arrivals", "same transaction count and byte volume", "same compute/NoC/paging settings", "same row and column address bits"],
        "limitations": ["multiple original Banks intentionally converge on the same timing-domain decoded Bank, while frontend physical addresses remain distinct", "timing stress only; no functional data-value simulation", "single deterministic captured cohort (n=1)"],
        "binary_sha256": sha256(BINARY),
        "ramulator_sha256": sha256(RAM),
    }
    (SUITE / "frozen_design.json").write_text(json.dumps(design, indent=2) + "\n")
    jobs = [(n, m, b, mode) for n, m, b in CASES for mode in ("normal", "oracle")]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        status = list(pool.map(run_one, jobs))
    (SUITE / "launcher_status.json").write_text(json.dumps(status, indent=2) + "\n")
    if any(row["returncode"] for row in status):
        raise SystemExit(1)
    print(json.dumps({"status": "PASS", "runs": len(status)}, indent=2))


if __name__ == "__main__":
    main()

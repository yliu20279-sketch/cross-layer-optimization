#!/usr/bin/env python3
import csv
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
LEVELS = [2048, 4096, 8192, 16384, 32768]
CASES = [(2, "steady", 0), (8, "bursty", 1101)]


def run(cmd):
    print("+", " ".join(map(str, cmd)), flush=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run(list(map(str, cmd)), check=True, cwd=ROOT, env=env)


def make_release(batch, mode, seed, out):
    src = HERE / "arrival_traces" / f"{mode}_c{batch}_seed{seed}.csv"
    rows = list(csv.DictReader(src.open(newline="")))[:batch]
    if len(rows) != batch:
        raise RuntimeError(f"insufficient arrivals in {src}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["owner", "release_cycle"])
        writer.writeheader()
        for owner, row in enumerate(rows):
            writer.writerow({"owner": owner, "release_cycle": row["arrival_cycle"]})
    return rows


def main():
    suite = ROOT / "results" / "bank_conflict_arrival_sampling_v2"
    suite.mkdir(parents=True, exist_ok=True)
    manifest = []
    for batch, mode, seed in CASES:
        release = suite / "releases" / f"{mode}_c{batch}_seed{seed}.csv"
        arrivals = make_release(batch, mode, seed, release)
        for sample in LEVELS:
            graph = suite / "graphs" / f"ctx128_c{batch}_{mode}_s{sample}"
            run([
                sys.executable, HERE / "build_arrival_sampling_graph.py",
                "--root", ROOT, "--context", 128, "--batch", batch,
                "--steps", 2, "--microbatch-size", 1,
                "--sample-bytes", sample, "--partition-capacity-mib", 512,
                "--cohort-policy", "exploratory_high_skew", "--cohort-repeat", 1,
                "--placement", ROOT / "results/sem_moe_reproduction_ctx128_v2/placement.json",
                "--compute-profile", ROOT / "scalesim_compute_profile_v1.json",
                "--hiband", "--out", graph,
            ])
            manifest.append({
                "context": 128, "batch": batch, "arrival_mode": mode,
                "arrival_seed": seed, "sample_bytes": sample,
                "transactions_per_full_sample": sample // 256,
                "graph": str(graph.relative_to(ROOT)),
                "release_file": str(release.relative_to(ROOT)),
                "last_release_cycle": int(arrivals[-1]["arrival_cycle"]),
            })
    (suite / "prepare_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "PASS", "graphs": len(manifest)}, indent=2))


if __name__ == "__main__":
    main()

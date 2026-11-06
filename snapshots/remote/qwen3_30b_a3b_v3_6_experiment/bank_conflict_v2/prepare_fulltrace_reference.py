#!/usr/bin/env python3
import csv
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
SUITE = ROOT / "results/bank_sampling_fulltrace_reference_v1"
CAPS = [4096, 16384, 65536, 262144, 1048576]


def run(command):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run(list(map(str, command)), cwd=ROOT, env=env, check=True)


def main():
    SUITE.mkdir(parents=True, exist_ok=True)
    records = []
    for batch in (2, 8):
        release = SUITE / f"c{batch}_simultaneous_release.csv"
        with release.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["owner", "release_cycle"])
            writer.writeheader()
            for owner in range(batch):writer.writerow({"owner": owner, "release_cycle": 0})
        for cap in CAPS + [None]:
            label = "full" if cap is None else f"s{cap}"
            graph = SUITE / "graphs" / f"ctx128_c{batch}_l1_t1_{label}"
            command = [
                sys.executable, HERE / "build_arrival_sampling_graph.py",
                "--root", ROOT, "--context", 128, "--batch", batch,
                "--steps", 1, "--layers", 1, "--microbatch-size", 1,
                "--partition-capacity-mib", 512,
                "--cohort-policy", "exploratory_high_skew", "--cohort-repeat", 1,
                "--placement", ROOT / "results/sem_moe_reproduction_ctx128_v2/placement.json",
                "--compute-profile", ROOT / "scalesim_compute_profile_v1.json",
                "--hiband", "--out", graph,
            ]
            if cap is None:command.append("--full-memory-trace")
            else:command += ["--sample-bytes", cap]
            run(command)
            records.append({"batch": batch, "layers": 1, "steps": 1, "sample_bytes_cap": cap, "full_memory_trace": cap is None, "graph": str(graph.relative_to(ROOT)), "release": str(release.relative_to(ROOT))})
    (SUITE / "prepare_manifest.json").write_text(json.dumps(records, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "graphs": len(records)}, indent=2))


if __name__ == "__main__":main()

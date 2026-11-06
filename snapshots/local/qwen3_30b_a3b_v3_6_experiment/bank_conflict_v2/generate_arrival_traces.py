#!/usr/bin/env python3
import csv
import hashlib
import json
import math
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SPEC_PATH = ROOT / "arrival_trace_spec.json"
OUT_DIR = ROOT / "arrival_traces"


def exp_interval(rng, mean):
    u = max(rng.random(), 1e-15)
    return max(1, int(round(-math.log(u) * mean)))


def rows_for(mode, concurrency, seed, count, config):
    rng = random.Random(seed)
    cycle = 0
    state = "burst"
    rows = []
    for request_id in range(count):
        rows.append({
            "request_id": request_id,
            "arrival_cycle": cycle,
            "target_concurrency": concurrency,
            "arrival_mode": mode,
            "seed": seed,
            "is_synthetic": "true",
        })
        if mode == "steady":
            delta = int(config["interarrival_cycles_by_concurrency"][str(concurrency)])
        elif mode == "poisson":
            mean = config["mean_interarrival_cycles_by_concurrency"][str(concurrency)]
            delta = exp_interval(rng, mean)
        elif mode == "bursty":
            base = config["base_interarrival_cycles_by_concurrency"][str(concurrency)]
            if state == "burst":
                mean = base * config["burst_interarrival_multiplier"]
                if rng.random() < config["burst_to_idle_probability"]:
                    state = "idle"
            else:
                mean = base * config["idle_interarrival_multiplier"]
                if rng.random() < config["idle_to_burst_probability"]:
                    state = "burst"
            delta = exp_interval(rng, mean)
        else:
            raise ValueError(f"unsupported mode: {mode}")
        cycle += delta
    return rows


def main():
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    fields = [
        "request_id", "arrival_cycle", "target_concurrency",
        "arrival_mode", "seed", "is_synthetic"
    ]
    for mode, config in spec["modes"].items():
        for concurrency in spec["target_concurrency"]:
            for seed in config["seeds"]:
                name = f"{mode}_c{concurrency}_seed{seed}.csv"
                path = OUT_DIR / name
                rows = rows_for(
                    mode, concurrency, seed, spec["request_count"], config
                )
                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                manifest.append({
                    "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                    "sha256": digest,
                    "rows": len(rows),
                    "first_cycle": rows[0]["arrival_cycle"],
                    "last_cycle": rows[-1]["arrival_cycle"],
                })
    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"generated {len(manifest)} traces in {OUT_DIR}")


if __name__ == "__main__":
    main()

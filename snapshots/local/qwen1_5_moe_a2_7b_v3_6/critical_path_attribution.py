#!/usr/bin/env python3
"""Conservative critical-path decomposition for coupled LegoSim runs."""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path


COMPONENTS = ("Compute", "NoC", "DRAM base", "Bank conflict/queue", "Sync/other")


def csv_rows(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", type=Path, required=True)
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    ops = {int(r["id"]): r for r in csv_rows(args.graph / "ops.csv")}
    events = {int(r["id"]): r for r in csv_rows(args.run / "events.csv")}
    parents = defaultdict(list)
    for edge in csv_rows(args.graph / "deps.csv"):
        parents[int(edge["dst"])].append(int(edge["src"]))
    manifest = json.loads((args.run / "run_manifest.json").read_text())
    bytes_per_cycle = float(manifest.get("base_memory_bytes_per_cycle", 102.4)) * float(manifest["dram_multiplier"])

    end = max(events, key=lambda i: (float(events[i]["done"]), i))
    chain = []
    cursor = end
    while True:
        chain.append(cursor)
        if not parents[cursor]:
            break
        ready = float(events[cursor]["ready"])
        cursor = max(parents[cursor], key=lambda i: (float(events[i]["done"]), i))
        if not math.isclose(float(events[cursor]["done"]), ready, abs_tol=1e-6):
            raise RuntimeError(f"critical predecessor mismatch at op {chain[-1]}")
    chain.reverse()

    components = {name: 0.0 for name in COMPONENTS}
    detail = []
    for op_id in chain:
        op, event = ops[op_id], events[op_id]
        ready, start, done = map(float, (event["ready"], event["start"], event["done"]))
        wait = max(0.0, start - ready)
        duration = max(0.0, done - start)
        kind = op["kind"]
        if kind == "COMPUTE":
            components["Compute"] += duration
            components["Sync/other"] += wait
        elif kind == "NET":
            components["NoC"] += wait + duration
        elif kind in ("LOAD", "STORE"):
            base = min(duration, math.ceil(float(op["bytes"]) / bytes_per_cycle))
            components["DRAM base"] += base
            components["Bank conflict/queue"] += wait + duration - base
        else:
            components["Sync/other"] += wait + duration
        detail.append({"op_id": op_id, "kind": kind, "task": op["task"], "ready": ready,
                       "start": start, "done": done, "wait": wait, "duration": duration})

    makespan = float(manifest["total_cycles"])
    attributed = sum(components.values())
    if not math.isclose(attributed, makespan, rel_tol=1e-10, abs_tol=1e-6):
        raise RuntimeError(f"non-conservative attribution: {attributed} != {makespan}")
    payload = {
        "schema_version": "critical-path-attribution-1.0",
        "definition": "latest-parent DAG critical path; memory residual above full-byte bandwidth floor is Bank conflict/queue",
        "makespan_cycles": makespan,
        "attributed_cycles": attributed,
        "conservation_error_cycles": attributed - makespan,
        "components": components,
        "critical_path_op_ids": chain,
        "detail": detail,
        "limitations": [
            "Bank conflict/queue is a conservative residual that includes per-partition bandwidth queue, DeepStack bank timing, and Ramulator backend overrun.",
            "Request-level same-bank overlap is reported separately and is not added to makespan.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("makespan_cycles", "components", "conservation_error_cycles")}, indent=2))


if __name__ == "__main__":
    main()

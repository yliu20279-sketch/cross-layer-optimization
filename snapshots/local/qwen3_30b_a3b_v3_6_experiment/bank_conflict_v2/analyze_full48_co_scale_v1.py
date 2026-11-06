#!/usr/bin/env python3
"""Build a conserving full-48-layer C+O scale table from paired runs."""
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCALE = ROOT / "results/bank_memory_stress_full48_co_scale_strict_v2"
CONCURRENCIES = (1, 2, 4, 8, 16)
COMPONENTS = (
    "Compute",
    "NoC",
    "DRAM service and non-cross-request memory wait",
    "Paging DMA",
    "Sync/other",
    "Strict cross-request Bank exposed",
)


def read_rows(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def run_paths(concurrency):
    graph = SCALE / "graphs" / f"c{concurrency}_co"
    return graph, SCALE / "runs" / f"c{concurrency}_normal", SCALE / "runs" / f"c{concurrency}_oracle"


def oracle_critical_path(graph, run):
    ops = {int(row["id"]): row for row in read_rows(graph / "ops.csv")}
    events = {int(row["id"]): row for row in read_rows(run / "events.csv")}
    parents = defaultdict(list)
    for edge in read_rows(graph / "deps.csv"):
        parents[int(edge["dst"])].append(int(edge["src"]))
    end = max(events, key=lambda key: (float(events[key]["done"]), key))
    chain, current = [], end
    while True:
        chain.append(current)
        if not parents[current]:
            break
        ready = float(events[current]["ready"])
        current = max(parents[current], key=lambda key: (float(events[key]["done"]), key))
        if not math.isclose(float(events[current]["done"]), ready, abs_tol=1e-6):
            raise RuntimeError("critical predecessor mismatch")
    chain.reverse()
    components = {key: 0.0 for key in COMPONENTS}
    for op_id in chain:
        op, event = ops[op_id], events[op_id]
        ready, start, done = map(float, (event["ready"], event["start"], event["done"]))
        wait, duration = max(0.0, start - ready), max(0.0, done - start)
        kind = op["kind"]
        if kind == "COMPUTE":
            components["Compute"] += duration
            components["Sync/other"] += wait
        elif kind == "NET":
            components["NoC"] += wait + duration
        elif kind in ("LOAD", "STORE"):
            components["DRAM service and non-cross-request memory wait"] += wait + duration
        elif kind in ("DMA_H2D", "DMA_D2H"):
            components["Paging DMA"] += wait + duration
        else:
            components["Sync/other"] += wait + duration
    total = float(json.loads((run / "run_manifest.json").read_text())["total_cycles"])
    if not math.isclose(sum(components.values()), total, abs_tol=1e-6):
        raise RuntimeError("oracle attribution does not conserve")
    return total, components


def paired_fairness(normal, oracle):
    left = json.loads((normal / "launch.json").read_text())
    right = json.loads((oracle / "launch.json").read_text())
    for key in ("binary_sha256", "ramulator_library_sha256", "graph_hashes", "deepstack_timing_sha256"):
        if left.get(key) != right.get(key):
            raise RuntimeError(f"{key} differs")
    left_controls, right_controls = dict(left["controls"]), dict(right["controls"])
    if right_controls.pop("HB_IGNORE_CROSS_REQUEST_BANK_TIMING", None) != "1":
        raise RuntimeError("oracle intervention flag missing")
    for controls in (left_controls, right_controls):
        controls.pop("HB_OUT", None)
        controls.pop("POPNET_STATS_DIR", None)
    if left_controls != right_controls:
        raise RuntimeError("non-intervention controls differ")


def bank_stats(path):
    rows = read_rows(path)
    return {
        "transactions": sum(int(row["transactions"]) for row in rows),
        "transactions_with_wait": sum(int(row["transactions_with_cross_request_wait"]) for row in rows),
        "represented_bytes": sum(int(row["represented_bytes"]) for row in rows),
        "controller_queue_ticks": sum(float(row["controller_queue_ticks"]) for row in rows),
        "cross_request_bank_wait_ticks": sum(float(row["cross_request_bank_wait_ticks"]) for row in rows),
    }


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    cases = []
    for concurrency in CONCURRENCIES:
        graph, normal, oracle = run_paths(concurrency)
        paired_fairness(normal, oracle)
        normal_validation = json.loads((normal / "validation.json").read_text())
        oracle_validation = json.loads((oracle / "validation.json").read_text())
        if normal_validation.get("status") != "PASS" or oracle_validation.get("status") != "PASS":
            raise RuntimeError(f"c{concurrency}: validation failed")
        normal_total = float(normal_validation["total_cycles"])
        oracle_total, components = oracle_critical_path(graph, oracle)
        exposed = normal_total - oracle_total
        if exposed < 0:
            raise RuntimeError(f"c{concurrency}: oracle slower than normal")
        components["Strict cross-request Bank exposed"] = exposed
        conservation_error = sum(components.values()) - normal_total
        if not math.isclose(conservation_error, 0.0, abs_tol=1e-6):
            raise RuntimeError(f"c{concurrency}: attribution does not conserve")
        stats = bank_stats(normal / "bank_aggregate.csv")
        cases.append({
            "concurrency": concurrency,
            "normal_cycles": normal_total,
            "oracle_cycles": oracle_total,
            "strict_bank_exposed_cycles": exposed,
            "strict_bank_exposed_fraction": exposed / normal_total if normal_total else 0.0,
            "speedup_normal_over_oracle": normal_total / oracle_total if oracle_total else None,
            "components": components,
            "conservation_error_cycles": conservation_error,
            "normal_bank": stats,
            "waited_transaction_fraction": stats["transactions_with_wait"] / stats["transactions"] if stats["transactions"] else 0.0,
            "cross_request_share_of_controller_queue": stats["cross_request_bank_wait_ticks"] / stats["controller_queue_ticks"] if stats["controller_queue_ticks"] else 0.0,
        })
    report = {
        "status": "PASS",
        "schema": "full48-co-scale-paired-conserving-attribution-v1",
        "definition": "Oracle critical-path components plus paired normal-minus-oracle delta; only the delta is strict cross-request Bank-conflict exposed time.",
        "workload": {
            "model": "Qwen3-30B-A3B",
            "layers": 48,
            "context": 512,
            "route_policy": "captured low-skew cohort",
            "compute_multiplier": 0.25,
            "max_outstanding_per_memory_op": 1,
            "memory_lanes": 0,
            "arrival_policy": "simultaneous",
            "classification": "synthetic C+O memory-stress, not natural serving",
        },
        "components_order": list(COMPONENTS),
        "cases": cases,
        "claim_boundary": [
            "Each bar is one deterministic captured cohort (n=1); no confidence interval is available.",
            "The stacked components conserve exactly to measured normal runtime.",
            "Only normal-minus-oracle is strict cross-request same-Bank critical-path exposure.",
            "C+O is a controlled memory-stress workload and must not be presented as a natural Qwen serving result.",
        ],
    }
    SCALE.mkdir(parents=True, exist_ok=True)
    report_path = SCALE / "scale_attribution.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    table_path = SCALE / "scale_components.csv"
    fields = [
        "concurrency", "normal_cycles", "oracle_cycles", *COMPONENTS,
        "strict_bank_exposed_fraction", "speedup_normal_over_oracle",
        "transactions", "transactions_with_wait", "waited_transaction_fraction",
        "represented_bytes", "controller_queue_ticks", "cross_request_bank_wait_ticks",
        "cross_request_share_of_controller_queue", "conservation_error_cycles",
    ]
    with table_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for case in cases:
            writer.writerow({
                "concurrency": case["concurrency"],
                "normal_cycles": case["normal_cycles"],
                "oracle_cycles": case["oracle_cycles"],
                **case["components"],
                "strict_bank_exposed_fraction": case["strict_bank_exposed_fraction"],
                "speedup_normal_over_oracle": case["speedup_normal_over_oracle"],
                **case["normal_bank"],
                "waited_transaction_fraction": case["waited_transaction_fraction"],
                "cross_request_share_of_controller_queue": case["cross_request_share_of_controller_queue"],
                "conservation_error_cycles": case["conservation_error_cycles"],
            })
    evidence = []
    for concurrency in CONCURRENCIES:
        graph, normal, oracle = run_paths(concurrency)
        for path in (
            graph / "ops.csv", graph / "deps.csv",
            normal / "validation.json", normal / "launch.json", normal / "run_manifest.json", normal / "events.csv", normal / "bank_aggregate.csv",
            oracle / "validation.json", oracle / "launch.json", oracle / "run_manifest.json", oracle / "events.csv", oracle / "bank_aggregate.csv",
        ):
            evidence.append({"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": sha256(path)})
    provenance_path = SCALE / "scale_provenance.json"
    provenance_path.write_text(json.dumps({"status": "EVIDENCE_COMPLETE", "files": evidence}, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "cases": len(cases), "table": str(table_path), "report": str(report_path)}, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import csv
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "results/bank_sampling_layer_stratified_v2"
LAYERS = [0, 8, 16, 24, 32, 40, 47]
LABELS = ["s4096", "s1048576", "full"]


def load(layer, label):
    run = SUITE / "runs" / f"layer{layer}_{label}"
    validation = json.loads((run / "validation.json").read_text())
    rows = list(csv.DictReader((run / "bank_aggregate.csv").open(newline="")))
    transactions = sum(int(row["transactions"]) for row in rows)
    waited = sum(int(row["transactions_with_cross_request_wait"]) for row in rows)
    wait_ticks = sum(float(row["cross_request_bank_wait_ticks"]) for row in rows)
    distribution = {
        (int(row["partition"]), int(row["bankgroup"]), int(row["bank"])): int(row["transactions"])
        for row in rows
    }
    return {
        "total_cycles": int(validation["total_cycles"]),
        "transactions": transactions,
        "transactions_with_wait": waited,
        "strict_wait_ticks": wait_ticks,
        "wait_ticks_per_transaction": wait_ticks / transactions,
        "waited_transaction_fraction": waited / transactions,
        "distribution": distribution,
    }


def js_divergence(left, right):
    keys = set(left) | set(right)
    left_total, right_total = sum(left.values()), sum(right.values())
    result = 0.0
    for key in keys:
        p, q = left.get(key, 0) / left_total, right.get(key, 0) / right_total
        midpoint = (p + q) / 2
        if p:result += 0.5 * p * math.log2(p / midpoint)
        if q:result += 0.5 * q * math.log2(q / midpoint)
    return result


def relative(value, reference):
    return (value - reference) / reference if reference else None


def main():
    output = []
    for layer in LAYERS:
        full = load(layer, "full")
        for label in LABELS:
            current = load(layer, label)
            output.append({
                "layer": layer,
                "sampling": label,
                "total_cycles": current["total_cycles"],
                "transactions": current["transactions"],
                "transactions_with_wait": current["transactions_with_wait"],
                "strict_wait_ticks": current["strict_wait_ticks"],
                "wait_ticks_per_transaction": current["wait_ticks_per_transaction"],
                "waited_transaction_fraction": current["waited_transaction_fraction"],
                "relative_total_cycle_error_vs_full": relative(current["total_cycles"], full["total_cycles"]),
                "relative_wait_per_transaction_error_vs_full": relative(current["wait_ticks_per_transaction"], full["wait_ticks_per_transaction"]),
                "relative_waited_fraction_error_vs_full": relative(current["waited_transaction_fraction"], full["waited_transaction_fraction"]),
                "bank_traffic_js_divergence_vs_full": js_divergence(current["distribution"], full["distribution"]),
            })
    csv_path = SUITE / "sampling_resolution.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output[0]))
        writer.writeheader();writer.writerows(output)
    one_mib = [row for row in output if row["sampling"] == "s1048576"]
    report = {
        "status": "RESOLVED_FULL_TRACE_REQUIRED",
        "scope": "Seven representative single-layer, one-step, c8 simultaneous-release traces.",
        "completed_runs": len(output),
        "layers": LAYERS,
        "decision": "Reject fixed-cap transaction sampling for strict Bank-conflict timing; use full transactions for mechanism evidence.",
        "one_mib_error_ranges": {
            "relative_wait_per_transaction": [min(row["relative_wait_per_transaction_error_vs_full"] for row in one_mib), max(row["relative_wait_per_transaction_error_vs_full"] for row in one_mib)],
            "relative_waited_transaction_fraction": [min(row["relative_waited_fraction_error_vs_full"] for row in one_mib), max(row["relative_waited_fraction_error_vs_full"] for row in one_mib)],
            "bank_traffic_js_divergence": [min(row["bank_traffic_js_divergence_vs_full"] for row in one_mib), max(row["bank_traffic_js_divergence_vs_full"] for row in one_mib)],
        },
        "observations": [
            "End-to-end cycles are unchanged because another modeled gate dominates; this is not evidence that strict Bank statistics converge.",
            "One MiB sampling reproduces Bank traffic distribution fairly closely but does not reproduce collision timing.",
            "Four KiB sampling can create severe false contention by synchronizing sparse sampled requests.",
            "A full 48-layer full-trace run was stopped after resource extrapolation showed it would exceed the configured two-hour timeout."
        ],
        "next_protocol": [
            "Use full transaction traces for layer-stratified Bank mechanism and distribution figures.",
            "Do not use sampled strict wait totals or sampled owner-shadow deltas as endpoint evidence.",
            "For full-model endpoint attribution, first replace the cycle-by-cycle driver with an event-driven or parallel memory replay validated against these full-trace layers."
        ]
    }
    report_path = SUITE / "sampling_resolution_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    paths = [csv_path, report_path, SUITE / "launcher_status.json"]
    for layer in LAYERS:
        for label in LABELS:
            run = SUITE / "runs" / f"layer{layer}_{label}"
            paths += [run / "validation.json", run / "launch.json", run / "bank_aggregate.csv"]
            graph = SUITE / "graphs" / f"layer{layer}_{label}"
            paths += [graph / "graph_manifest.json", graph / "ops.csv", graph / "deps.csv", graph / "address_manifest.csv"]
    provenance = [{"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in paths]
    provenance_path = SUITE / "sampling_resolution_provenance.json"
    provenance_path.write_text(json.dumps({"status": "EVIDENCE_COMPLETE", "experiment_status": report["status"], "files": provenance}, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "rows": len(output), "provenance_files": len(provenance)}, indent=2))


if __name__ == "__main__":main()

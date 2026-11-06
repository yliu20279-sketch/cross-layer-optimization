#!/usr/bin/env python3
"""Summarize c4 address-mapping screen and select the highest strict exposure."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "results/bank_alias_pressure_screen_c4_v2"
CASES = ("balanced16", "effective16", "effective8", "effective4", "effective2")


def rows(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def bank_stats(path):
    data = rows(path)
    transactions = sum(int(x["transactions"]) for x in data)
    waited = sum(int(x["transactions_with_cross_request_wait"]) for x in data)
    wait_ticks = sum(float(x["cross_request_bank_wait_ticks"]) for x in data)
    queue_ticks = sum(float(x["controller_queue_ticks"]) for x in data)
    active_cells = sum(int(x["transactions"]) > 0 for x in data)
    decoded_banks = {int(x["bankgroup"]) * 4 + int(x["bank"]) for x in data if int(x["transactions"]) > 0}
    return {
        "transactions": transactions,
        "waited_transactions": waited,
        "waited_transaction_fraction": waited / transactions,
        "cross_request_bank_wait_ticks": wait_ticks,
        "controller_queue_ticks": queue_ticks,
        "cross_request_share_of_controller_queue": wait_ticks / queue_ticks,
        "active_partition_bank_cells": active_cells,
        "observed_decoded_banks": sorted(decoded_banks),
    }


def main():
    design = json.loads((SUITE / "frozen_design.json").read_text())
    out = []
    for case in CASES:
        normal = SUITE / "runs" / f"{case}_normal"
        oracle = SUITE / "runs" / f"{case}_oracle"
        nv = json.loads((normal / "validation.json").read_text())
        ov = json.loads((oracle / "validation.json").read_text())
        nl = json.loads((normal / "launch.json").read_text())
        ol = json.loads((oracle / "launch.json").read_text())
        if nv["status"] != "PASS" or ov["status"] != "PASS":
            raise RuntimeError(f"{case}: validation failed")
        if nl["binary_sha256"] != ol["binary_sha256"] or nl["ramulator_library_sha256"] != ol["ramulator_library_sha256"] or nl["graph_hashes"] != ol["graph_hashes"]:
            raise RuntimeError(f"{case}: paired evidence differs")
        n, o = float(nv["total_cycles"]), float(ov["total_cycles"])
        stats = bank_stats(normal / "bank_aggregate.csv")
        out.append({
            "case": case,
            "mapping": nl["controls"]["HB_BANK_ADDRESS_MODE"],
            "effective_banks": int(nl["controls"]["HB_EFFECTIVE_BANKS"]),
            "normal_cycles": n,
            "oracle_cycles": o,
            "strict_exposed_cycles": n - o,
            "strict_exposed_fraction": (n - o) / n,
            **stats,
        })
    candidates = [x for x in out if x["mapping"] == "alias"]
    winner = max(candidates, key=lambda x: x["strict_exposed_fraction"])
    report = {
        "status": "PASS",
        "classification": design["classification"],
        "selection_rule": "maximum strict paired normal-minus-oracle end-to-end fraction among alias cases",
        "cases": out,
        "winner": winner,
        "target_30_percent_reached": winner["strict_exposed_fraction"] >= 0.30,
    }
    (SUITE / "screen_report.json").write_text(json.dumps(report, indent=2) + "\n")
    with (SUITE / "screen_results.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(out[0]))
        writer.writeheader()
        writer.writerows(out)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

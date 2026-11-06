#!/usr/bin/env python3
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def load_json(path):
    return json.loads(path.read_text())


def bank_stats(path):
    totals = defaultdict(lambda: {"transactions": 0, "strict_wait_ticks": 0})
    transaction_count = 0
    queue_ticks = 0
    strict_wait_ticks = 0
    max_depart_tick = 0
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            transaction_count += 1
            queue_ticks += int(row["controller_queue_ticks"])
            wait = int(row["cross_request_bank_wait_ticks"])
            strict_wait_ticks += wait
            max_depart_tick = max(max_depart_tick, int(row["controller_depart_tick"]))
            key = ":".join(row[name] for name in ("partition", "channel", "rank", "bankgroup", "bank"))
            totals[key]["transactions"] += 1
            totals[key]["strict_wait_ticks"] += wait
    ranked = sorted(totals.items(), key=lambda item: item[1]["strict_wait_ticks"], reverse=True)
    top8_wait = sum(value["strict_wait_ticks"] for _, value in ranked[:8])
    return {
        "transactions": transaction_count,
        "sum_queue_ticks": queue_ticks,
        "sum_strict_wait_ticks": strict_wait_ticks,
        "max_depart_tick": max_depart_tick,
        "active_banks": len(totals),
        "nonzero_wait_banks": sum(value["strict_wait_ticks"] > 0 for value in totals.values()),
        "top8_strict_wait_ticks": top8_wait,
        "top8_strict_wait_fraction": top8_wait / strict_wait_ticks if strict_wait_ticks else 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    paths = {mode: args.pair / mode for mode in ("normal", "oracle")}
    launches = {mode: load_json(path / "launch.json") for mode, path in paths.items()}
    validations = {mode: load_json(path / "validation.json") for mode, path in paths.items()}
    failures = []
    for key in ("binary_sha256", "ramulator_library_sha256", "graph_hashes", "deepstack_timing_sha256"):
        if launches["normal"].get(key) != launches["oracle"].get(key):
            failures.append(f"{key} differs")
    normal_controls = dict(launches["normal"]["controls"])
    oracle_controls = dict(launches["oracle"]["controls"])
    if oracle_controls.pop("HB_IGNORE_CROSS_REQUEST_BANK_TIMING", None) != "1":
        failures.append("oracle flag missing")
    for controls in (normal_controls, oracle_controls):
        controls.pop("HB_OUT", None)
        controls.pop("POPNET_STATS_DIR", None)
    if normal_controls != oracle_controls:
        failures.append("non-intervention controls differ")
    if any(result.get("status") != "PASS" for result in validations.values()):
        failures.append("one or more execution validations failed")
    stats = {mode: bank_stats(path / "bank_requests.csv") for mode, path in paths.items()}
    normal_cycles = validations["normal"]["total_cycles"]
    oracle_cycles = validations["oracle"]["total_cycles"]
    exposed = normal_cycles - oracle_cycles
    report = {
        "schema": "single-owner-shadow-paired-audit-v1",
        "status": "FAIL" if failures else "PASS",
        "failures": failures,
        "normal_cycles": normal_cycles,
        "oracle_cycles": oracle_cycles,
        "exposed_cross_request_bank_cycles": exposed,
        "exposed_fraction": exposed / normal_cycles,
        "normal_bank": stats["normal"],
        "oracle_bank": stats["oracle"],
        "claim_boundary": "End-to-end sensitivity to an owner-isolated Bank timing/row-state oracle; not a realizable hardware configuration and not equal to summed request wait.",
    }
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()

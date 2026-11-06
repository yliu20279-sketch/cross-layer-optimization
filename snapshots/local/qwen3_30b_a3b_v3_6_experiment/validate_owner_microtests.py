#!/usr/bin/env python3
"""Validate request-owner propagation without claiming Bank contention."""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def rows(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--graphs", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    report = {"schema": "owner-propagation-validation-v1", "cases": {}}
    failures = []
    for graph_dir in sorted(p for p in args.graphs.iterdir() if p.is_dir()):
        result_dir = args.results / graph_dir.name
        expected_by_op = {
            int(r["id"]): int(r["inference_request_id"])
            for r in rows(graph_dir / "ops.csv")
        }
        event_rows = rows(result_dir / "events.csv")
        bank_rows = rows(result_dir / "bank_requests.csv")
        event_by_op = {int(r["id"]): int(r["inference_request_id"]) for r in event_rows}
        bank_by_op = defaultdict(set)
        for row in bank_rows:
            bank_by_op[int(row["op_id"])].add(int(row["inference_request_id"]))

        case_failures = []
        if event_by_op != expected_by_op:
            case_failures.append("events.csv owner mismatch")
        for op_id, owner in expected_by_op.items():
            if not bank_by_op[op_id]:
                case_failures.append(f"op {op_id} has no sampled Bank transactions")
            elif bank_by_op[op_id] != {owner}:
                case_failures.append(
                    f"op {op_id} Bank owners {sorted(bank_by_op[op_id])} != {owner}"
                )
        report["cases"][graph_dir.name] = {
            "status": "FAIL" if case_failures else "PASS",
            "expected_owner_by_op": expected_by_op,
            "event_owner_by_op": event_by_op,
            "bank_owner_by_op": {str(k): sorted(v) for k, v in bank_by_op.items()},
            "sampled_transactions": len(bank_rows),
            "failures": case_failures,
        }
        failures.extend(f"{graph_dir.name}: {x}" for x in case_failures)

    report["status"] = "FAIL" if failures else "PASS"
    report["claim_boundary"] = (
        "This validates inference-request ownership propagation only. It does not "
        "measure or validate cross-request same-Bank contention overhead."
    )
    report["failures"] = failures
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import argparse, csv, json
from pathlib import Path

EXPECTED = {
    "different_owner_same_bank_overlap": "positive",
    "same_owner_same_bank_overlap": "zero",
    "different_owner_different_partition": "zero",
    "single_owner_row_switch": "zero",
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    report = {"schema": "strict-bank-microtest-v1", "cases": {}}
    failures = []
    for case, oracle in EXPECTED.items():
        with (a.results / case / "bank_requests.csv").open(newline="") as f:
            rows = list(csv.DictReader(f))
        waits = [int(r["cross_request_bank_wait_ticks"]) for r in rows]
        events = [int(r["cross_request_bank_wait_events"]) for r in rows]
        total = sum(waits)
        passed = total > 0 if oracle == "positive" else total == 0
        if not passed:
            failures.append(f"{case}: expected {oracle}, observed {total}")
        report["cases"][case] = {
            "status": "PASS" if passed else "FAIL",
            "oracle": oracle,
            "transactions": len(rows),
            "strict_wait_ticks": total,
            "strict_wait_events": sum(events),
            "nonzero_transactions": sum(x > 0 for x in waits),
        }
    report["status"] = "FAIL" if failures else "PASS"
    report["failures"] = failures
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(1 if failures else 0)

if __name__ == "__main__":
    main()

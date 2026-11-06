#!/usr/bin/env python3
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "results/bank_conflict_arrival_sampling_v2"
LEVELS = [2048, 4096, 8192, 16384, 32768]
PAT = re.compile(r"S\d+L\d+W(\d+)")


def read_rows(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def overlap(events):
    spans = {}
    for row in events:
        match = PAT.search(row["task"])
        if not match:
            continue
        owner = int(match.group(1))
        span = spans.setdefault(owner, [float("inf"), 0.0])
        span[0] = min(span[0], float(row["start"]))
        span[1] = max(span[1], float(row["done"]))
    points = sorted((t, d) for a, b in spans.values() for t, d in ((a, 1), (b, -1)))
    first, last = min(a for a, _ in spans.values()), max(b for _, b in spans.values())
    active = 0
    prior = first
    area = 0.0
    ge2 = 0.0
    maximum = 0
    for tick, delta in points:
        duration = tick - prior
        area += active * duration
        if active >= 2:
            ge2 += duration
        active += delta
        maximum = max(maximum, active)
        prior = tick
    makespan = last - first
    return {
        "requests_observed": len(spans),
        "max_active_requests": maximum,
        "time_weighted_mean_active": area / makespan,
        "overlap_fraction_ge2": ge2 / makespan,
        "makespan_cycles": makespan,
    }


def summarize(batch, sample):
    mode = "finite_overlap" if batch == 2 else "bursty"
    run = SUITE / "runs" / f"ctx128_c{batch}_{mode}_s{sample}_normal"
    validation = json.loads((run / "validation.json").read_text())
    bank = read_rows(run / "bank_requests.csv")
    waits = [float(row["cross_request_bank_wait_ticks"]) for row in bank]
    wait_events = [int(row["cross_request_bank_wait_events"]) for row in bank]
    partitions = defaultdict(lambda: [0, 0.0])
    for row, wait in zip(bank, waits):
        key = (int(row["partition"]), int(row["bankgroup"]), int(row["bank"]))
        partitions[key][0] += 1
        partitions[key][1] += wait
    wait_by_bank = sorted((value[1] for value in partitions.values()), reverse=True)
    row = {
        "batch": batch,
        "mode": mode,
        "sample_bytes": sample,
        "transactions_per_large_op": sample // 256,
        "total_cycles": int(validation["total_cycles"]),
        "transactions": len(bank),
        "strict_wait_ticks_sum": sum(waits),
        "strict_wait_events_sum": sum(wait_events),
        "transactions_with_strict_wait": sum(x > 0 for x in waits),
        "active_partition_banks": len(partitions),
        "top8_strict_wait_share": sum(wait_by_bank[:8]) / sum(wait_by_bank) if sum(wait_by_bank) else 0.0,
    }
    row.update(overlap(read_rows(run / "events.csv")))
    return row


def main():
    rows = [summarize(batch, sample) for batch in (2, 8) for sample in LEVELS]
    for batch in (2, 8):
        group = [row for row in rows if row["batch"] == batch]
        for index, row in enumerate(group):
            if index == 0:
                row["adjacent_total_change"] = None
                row["adjacent_wait_change"] = None
            else:
                prev = group[index - 1]
                row["adjacent_total_change"] = (row["total_cycles"] - prev["total_cycles"]) / prev["total_cycles"]
                denom = prev["strict_wait_ticks_sum"]
                row["adjacent_wait_change"] = ((row["strict_wait_ticks_sum"] - denom) / denom) if denom else None
    fields = list(rows[0])
    with (SUITE / "sampling_convergence.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    converged = all(
        abs([row for row in rows if row["batch"] == batch][-1]["adjacent_wait_change"]) <= 0.05
        for batch in (2, 8)
    )
    report = {
        "status": "CONVERGED" if converged else "NOT_CONVERGED",
        "rows": rows,
        "criteria": {
            "adjacent_total_abs_max": 0.01,
            "adjacent_strict_wait_abs_max": 0.05,
            "note": "Endpoint counterfactual convergence is not tested by normal-only runs."
        },
        "limitations": [
            "Finite c2/c8 request windows, not a 128-request steady-state service trace.",
            "Request spans are inferred from W-index task names.",
            "The offline deterministic paging schedule is not an online scheduler."
        ]
    }
    (SUITE / "step4_6_report.json").write_text(json.dumps(report, indent=2) + "\n")
    evidence = []
    for path in sorted(SUITE.rglob("*")):
        if path.is_file() and path.name not in {"step4_6_provenance.json"}:
            evidence.append({"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (SUITE / "step4_6_provenance.json").write_text(json.dumps({"status": "EVIDENCE_COMPLETE", "experiment_status": report["status"], "files": evidence}, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "cases": len(rows), "provenance_files": len(evidence)}, indent=2))


if __name__ == "__main__":
    main()

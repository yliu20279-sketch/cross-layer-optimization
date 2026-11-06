#!/usr/bin/env python3
"""Read-only audit for cross-user expert-page Bank-layout evidence.

This script intentionally does not estimate layout speedup.  The retained
full-trace artifacts do not contain transaction-level page and Bank identity
in the same record, so such an estimate would not be evidence-backed.
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "results" / "bank_fulltrace_c8_bursty_v1"
EVENTS = SUITE / "normal_eventjump_v6" / "events.csv"
PAIR_REPORT = SUITE / "full48_pair_analysis" / "report.json"
OUT = Path(__file__).resolve().parent / "audit_results.json"

# Example: S0L25W3E117_weight_read
EXPERT_RE = re.compile(r"^S(?P<step>\d+)L(?P<layer>\d+)W(?P<owner>\d+)E(?P<expert>\d+)_weight_read$")


def load_accesses() -> list[dict]:
    accesses = []
    with EVENTS.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            match = EXPERT_RE.match(row["task"])
            if not match:
                continue
            owner = int(row["inference_request_id"])
            task_owner = int(match.group("owner"))
            if owner != task_owner:
                raise AssertionError((row["task"], owner, task_owner))
            start = float(row["start"])
            done = float(row["backend_done"])
            if done < start:
                raise AssertionError((row["id"], start, done))
            accesses.append(
                {
                    "op_id": int(row["id"]),
                    "owner": owner,
                    "partition": int(row["pe"]),
                    "page": (int(match.group("layer")), int(match.group("expert"))),
                    "start": start,
                    "done": done,
                    "bytes": int(row["bytes"]),
                }
            )
    return accesses


def overlap_audit(accesses: list[dict]) -> dict:
    by_partition = defaultdict(list)
    for access in accesses:
        by_partition[access["partition"]].append(access)

    pair_counts = Counter()
    overlap_cycles = Counter()
    examples = {"same_page": [], "distinct_page": []}
    for partition, rows in by_partition.items():
        rows.sort(key=lambda item: (item["start"], item["done"], item["op_id"]))
        active = []
        for current in rows:
            active = [prior for prior in active if prior["done"] > current["start"]]
            for prior in active:
                if prior["owner"] == current["owner"]:
                    continue
                overlap = min(prior["done"], current["done"]) - max(prior["start"], current["start"])
                if overlap <= 0:
                    continue
                kind = "same_page" if prior["page"] == current["page"] else "distinct_page"
                pair_counts[kind] += 1
                overlap_cycles[kind] += overlap
                if len(examples[kind]) < 5:
                    examples[kind].append(
                        {
                            "partition": partition,
                            "owners": [prior["owner"], current["owner"]],
                            "pages": [list(prior["page"]), list(current["page"])],
                            "overlap_cycles": overlap,
                        }
                    )
            active.append(current)

    total_pairs = sum(pair_counts.values())
    total_overlap = sum(overlap_cycles.values())
    return {
        "cross_user_overlapping_access_pairs": dict(pair_counts),
        "cross_user_overlap_cycles_pair_sum": dict(overlap_cycles),
        "distinct_page_pair_fraction": pair_counts["distinct_page"] / total_pairs if total_pairs else None,
        "distinct_page_overlap_fraction": overlap_cycles["distinct_page"] / total_overlap if total_overlap else None,
        "examples": examples,
        "interpretation_limit": (
            "These are operation-level expert-weight service-window overlaps, not transaction-level "
            "same-Bank conflicts. Distinct-page overlap is only a necessary opportunity indicator."
        ),
    }


def main() -> None:
    accesses = load_accesses()
    pair = json.loads(PAIR_REPORT.read_text(encoding="utf-8"))
    result = {
        "status": "PASS_WITH_EVIDENCE_GAP",
        "workload": {
            "model": "Qwen3-30B-A3B-derived diagnostic",
            "routing": "captured Qwen3 cohorts",
            "arrival": "synthetic bursty c8, seed 1101",
            "address_mapping": "native",
            "classification": "hybrid diagnostic; not a natural production serving trace",
        },
        "observed_fields": {
            "event_level": [
                "inference_request_id",
                "task-encoded layer/expert page identity",
                "partition/PE",
                "start",
                "backend_done",
                "bytes",
            ],
            "bank_aggregate_level": [
                "partition",
                "bankgroup",
                "bank",
                "cross_request_bank_wait_ticks",
                "row_status counts",
            ],
        },
        "missing_join_fields": [
            "transaction-level expert_page_id in retained Bank logs",
            "transaction-level decoded Bank joined to expert_page_id",
            "blocking transaction/page/request identity",
            "per-layout row-buffer and Bank-wait logs",
        ],
        "expert_accesses": {
            "count": len(accesses),
            "owners": sorted({item["owner"] for item in accesses}),
            "unique_pages": len({item["page"] for item in accesses}),
            "partitions": len({item["partition"] for item in accesses}),
            "represented_bytes": sum(item["bytes"] for item in accesses),
        },
        "overlap_proxy": overlap_audit(accesses),
        "paired_bank_intervention": {
            "normal_cycles": pair["normal_cycles"],
            "oracle_cycles": pair["oracle_cycles"],
            "exposed_cross_request_bank_cycles": pair["exposed_cross_request_bank_cycles"],
            "exposed_fraction": pair["exposed_fraction"],
            "cumulative_cross_request_bank_wait_ticks": pair["cumulative_cross_request_bank_wait_ticks"],
            "requests_with_positive_completion_delta": pair["requests_with_positive_completion_delta"],
            "upper_bound_note": (
                "For this exact run, a layout that removes only cross-request same-Bank timing "
                "cannot be credited with more end-to-end gain than the paired oracle delta."
            ),
        },
        "four_layout_experiment_status": "NOT_EXECUTABLE_FROM_RETAINED_ARTIFACTS",
        "reason": (
            "The saved full48 graph/address_manifest and transaction-detail Bank log are absent. "
            "Changing or evaluating page-to-Bank placement would therefore require regenerating the "
            "graph and rerunning the instrumented simulator, not post-processing current outputs."
        ),
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

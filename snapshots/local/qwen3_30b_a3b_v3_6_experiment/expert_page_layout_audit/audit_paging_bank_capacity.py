#!/usr/bin/env python3
"""Replay a frozen paging schedule against static expert-page Bank ownership."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph-manifest", type=Path, required=True)
    parser.add_argument("--placement", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    graph = json.loads(args.graph_manifest.read_text())
    placement = json.loads(args.placement.read_text())
    slots = graph["budget"]["cache_slots_per_partition"]
    page_bytes = graph["budget"]["expert_page_bytes"]
    bank_capacity = (512 * 2**20 // 16) // page_bytes
    pages_by_rank = defaultdict(list)
    for layer in range(48):
        for expert in range(128):
            rank = int(placement[str(layer)]["expert_to_rank"][str(expert)])
            pages_by_rank[rank].append((layer, expert))
    bank_of = {}
    resident = {}
    counts = defaultdict(Counter)
    maxima = defaultdict(Counter)
    for rank, pages in pages_by_rank.items():
        pages.sort()
        for index, page in enumerate(pages):
            bank_of[page] = index % 16
        resident[rank] = set(pages[:slots])
        for page in resident[rank]:
            counts[rank][bank_of[page]] += 1
        maxima[rank].update(counts[rank])
    first_violation = None
    for event_index, event in enumerate(graph["page_operations"]):
        rank = int(event["rank"])
        page = tuple(event["page"])
        victim = tuple(event["victim"])
        assert page not in resident[rank]
        assert victim in resident[rank]
        resident[rank].remove(victim)
        counts[rank][bank_of[victim]] -= 1
        resident[rank].add(page)
        counts[rank][bank_of[page]] += 1
        assert sum(counts[rank].values()) == slots
        for bank, count in counts[rank].items():
            maxima[rank][bank] = max(maxima[rank][bank], count)
            if count > bank_capacity and first_violation is None:
                first_violation = {"event_index": event_index, "rank": rank,
                                   "bank": bank, "resident_pages": count,
                                   "incoming_page": page, "victim": victim}
    report = {
        "status": "PASS" if first_violation is None else "CAPACITY_VIOLATION",
        "policy": "static round-robin by sorted page index within partition",
        "partition_capacity_bytes": 512 * 2**20,
        "per_bank_page_capacity": bank_capacity,
        "resident_pages_per_partition": slots,
        "page_operations": len(graph["page_operations"]),
        "peak_resident_pages_in_any_bank": max(max(x.values()) for x in maxima.values()),
        "first_violation": first_violation,
        "limit": "The original global-LRU victim schedule is replayed; a different pager could alter occupancy.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

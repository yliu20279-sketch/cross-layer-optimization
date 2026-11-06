#!/usr/bin/env python3
"""Derive held-out heat and overlap-aware Bank assignments from a profile run.

The profile and evaluation cohorts must be disjoint. This script does not inspect
evaluation events, and it preserves the fixed expert-to-partition placement.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path


WEIGHT = re.compile(r"^S\d+L(?P<layer>\d+)W\d+E(?P<expert>\d+)_weight_read$")
BANKS = 16
CAPACITY = 14


def load_profile(path: Path, page_rank: dict[tuple[int, int], int]):
    intervals = defaultdict(list)
    heat = defaultdict(float)
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            match = WEIGHT.match(row["task"])
            if not match:
                continue
            page = (int(match["layer"]), int(match["expert"]))
            start, done = float(row["start"]), float(row["done"])
            if not (0 <= start <= done):
                raise ValueError(f"invalid expert interval: {page}")
            rank = page_rank[page]
            owner = int(row["inference_request_id"])
            intervals[rank].append((start, done, page, owner))
            heat[page] += 1.0
    return intervals, heat


def overlap_weights(intervals):
    weights = defaultdict(float)
    for rank, entries in intervals.items():
        active = []
        for start, done, page, owner in sorted(entries):
            active = [entry for entry in active if entry[0] > start]
            for other_done, other_page, other_owner in active:
                if owner == other_owner or page == other_page:
                    continue
                pair = tuple(sorted((page, other_page)))
                weights[rank, pair] += min(done, other_done) - start
            active.append((done, page, owner))
    return weights


def assign(pages_by_rank, heat, overlap, initial, coaccess_weight):
    result = {}
    diagnostics = {}
    for rank in range(16):
        pages = pages_by_rank[rank]
        total = sum(heat[p] for p in pages)
        norm = max(total / BANKS, 1.0)
        # Initial resident pages must fit 14 pages per Bank. Infrequent cold
        # pages are assigned last, but still get a deterministic Bank.
        order = sorted(pages, key=lambda p: (-heat[p], p not in initial[rank], p))
        load = [0.0] * BANKS
        initial_count = [0] * BANKS
        for page in order:
            candidates = [b for b in range(BANKS)
                          if page not in initial[rank] or initial_count[b] < CAPACITY]
            if not candidates:
                raise ValueError(f"initial residency exceeds Bank capacity at rank {rank}")
            def score(bank):
                projected = (load[bank] + heat[page]) / norm
                pair_cost = sum(
                    overlap.get((rank, tuple(sorted((page, other)))), 0.0)
                    for other in pages if other in result and result[other] == bank
                )
                return (projected ** 2 + coaccess_weight * pair_cost / norm,
                        initial_count[bank], bank)
            bank = min(candidates, key=score)
            result[page] = bank
            load[bank] += heat[page]
            if page in initial[rank]:
                initial_count[bank] += 1
        diagnostics[rank] = {"heat_min": min(load), "heat_max": max(load),
                             "max_initial_resident": max(initial_count)}
    return result, diagnostics


def save(path, page_rank, assignment):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("layer", "expert", "partition", "bank"))
        for page in sorted(page_rank):
            writer.writerow((*page, page_rank[page], assignment[page]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--placement", required=True, type=Path)
    parser.add_argument("--profile-events", required=True, type=Path)
    parser.add_argument("--cache-slots-per-partition", required=True, type=int)
    parser.add_argument("--out-heat", required=True, type=Path)
    parser.add_argument("--out-coaccess", required=True, type=Path)
    parser.add_argument("--out-summary", required=True, type=Path)
    args = parser.parse_args()
    placement = json.loads(args.placement.read_text())
    page_rank = {}
    pages_by_rank = defaultdict(list)
    for layer in range(48):
        for expert in range(128):
            rank = int(placement[str(layer)]["expert_to_rank"][str(expert)])
            page = (layer, expert)
            page_rank[page] = rank
            pages_by_rank[rank].append(page)
    initial = {rank: set(sorted(pages)[:args.cache_slots_per_partition])
               for rank, pages in pages_by_rank.items()}
    intervals, heat = load_profile(args.profile_events, page_rank)
    observed_pages = len(heat)
    observed_reads = int(sum(heat.values()))
    overlap = overlap_weights(intervals)
    heat_assignment, heat_diag = assign(pages_by_rank, heat, overlap, initial, 0.0)
    co_assignment, co_diag = assign(pages_by_rank, heat, overlap, initial, 1.0)
    save(args.out_heat, page_rank, heat_assignment)
    save(args.out_coaccess, page_rank, co_assignment)
    summary = {"status": "PASS", "profile_expert_reads": observed_reads,
               "profile_distinct_pages": observed_pages, "coaccess_edges": len(overlap),
               "changed_from_heat": sum(heat_assignment[p] != co_assignment[p]
                                        for p in page_rank),
               "heat_diagnostics": heat_diag, "coaccess_diagnostics": co_diag}
    args.out_summary.parent.mkdir(parents=True, exist_ok=True)
    args.out_summary.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

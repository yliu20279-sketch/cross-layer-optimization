#!/usr/bin/env python3
"""Held-out, fixed-timeline test of overlap-aware expert-page Bank placement.

This is a mechanism test, not an end-to-end replay: event times are held fixed and
therefore do not include any changed pager DAG or feedback from Bank arbitration.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

from derive_profile_assignments import assign, load_profile, overlap_weights


def read_layout(path: Path):
    layout, pages_by_rank = {}, defaultdict(list)
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            page = (int(row["layer"]), int(row["expert"]))
            rank = int(row["partition"])
            layout[page] = (rank, int(row["bank"]))
            pages_by_rank[rank].append(page)
    return layout, pages_by_rank


def score(overlap, assignment):
    total = sum(overlap.values())
    within = sum(weight for (rank, (a, b)), weight in overlap.items()
                 if assignment[a] == assignment[b])
    return {"total_overlap": total, "same_bank_overlap": within,
            "same_bank_fraction": within / total if total else None}


def shuffled_overlap(overlap, pages_by_rank, rng):
    permutation = {}
    for rank, pages in pages_by_rank.items():
        originals = sorted(pages)
        changed = originals[:]
        rng.shuffle(changed)
        permutation.update(zip(originals, changed))
    result = defaultdict(float)
    for (rank, (a, b)), weight in overlap.items():
        pair = tuple(sorted((permutation[a], permutation[b])))
        result[rank, pair] += weight
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-events", required=True, type=Path)
    parser.add_argument("--evaluation-events", required=True, type=Path)
    parser.add_argument("--trace-label", default="evaluation")
    parser.add_argument("--cache-slots-per-partition", type=int, default=187)
    parser.add_argument("--heat-layout", required=True, type=Path)
    parser.add_argument("--coaccess-layout", required=True, type=Path)
    parser.add_argument("--round-robin-layout", required=True, type=Path)
    parser.add_argument("--permutations", type=int, default=0)
    parser.add_argument("--seed", type=int, default=20261011)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    heat_layout, pages_by_rank = read_layout(args.heat_layout)
    co_layout, co_pages = read_layout(args.coaccess_layout)
    rr_layout, rr_pages = read_layout(args.round_robin_layout)
    if set(heat_layout) != set(co_layout) or set(heat_layout) != set(rr_layout):
        raise ValueError("layouts cover different expert pages")
    if any(heat_layout[p][0] != co_layout[p][0] or
           heat_layout[p][0] != rr_layout[p][0] for p in heat_layout):
        raise ValueError("expert-to-partition placement differs")
    page_rank = {p: rank for p, (rank, _) in heat_layout.items()}
    profile_intervals, profile_heat = load_profile(args.profile_events, page_rank)
    eval_intervals, eval_heat = load_profile(args.evaluation_events, page_rank)
    profile_overlap = overlap_weights(profile_intervals)
    eval_overlap = overlap_weights(eval_intervals)
    matched_edges = set(profile_overlap) & set(eval_overlap)
    evaluation_weight = sum(eval_overlap.values())
    assignments = {
        "heat": {p: bank for p, (_, bank) in heat_layout.items()},
        "coaccess": {p: bank for p, (_, bank) in co_layout.items()},
        "round_robin": {p: bank for p, (_, bank) in rr_layout.items()},
    }
    rng = random.Random(args.seed)
    initial = {rank: set(sorted(pages)[:args.cache_slots_per_partition])
               for rank, pages in pages_by_rank.items()}
    oracle_assignment, _ = assign(pages_by_rank, eval_heat, eval_overlap,
                                  initial, 1.0)
    null_scores = []
    null_changes = []
    for _ in range(args.permutations):
        shuffled = shuffled_overlap(profile_overlap, pages_by_rank, rng)
        null_assignment, _ = assign(pages_by_rank, profile_heat, shuffled,
                                    initial, 1.0)
        null_scores.append(score(eval_overlap, null_assignment)["same_bank_overlap"])
        null_changes.append(sum(null_assignment[p] != assignments["heat"][p]
                                for p in page_rank))
    observed = score(eval_overlap, assignments["coaccess"])["same_bank_overlap"]
    changed = {p for p in page_rank
               if assignments["coaccess"][p] != assignments["heat"][p]}
    touched = [(weight, a, b) for (_, (a, b)), weight in eval_overlap.items()
               if a in changed or b in changed]
    affected = [(weight, a, b) for weight, a, b in touched
                if (assignments["heat"][a] == assignments["heat"][b]) !=
                   (assignments["coaccess"][a] == assignments["coaccess"][b])]
    result = {
        "interpretation": "Fixed observed timeline; overlap proxy only, not Bank wait or end-to-end cycles",
        "trace_label": args.trace_label,
        "profile_reads": int(sum(profile_heat.values())),
        "evaluation_reads": int(sum(eval_heat.values())),
        "profile_overlap_edges": len(profile_overlap),
        "evaluation_overlap_edges": len(eval_overlap),
        "profile_to_evaluation_edge_coverage": {
            "matched_edges": len(matched_edges),
            "evaluation_edge_fraction": len(matched_edges) / len(eval_overlap) if eval_overlap else None,
            "evaluation_overlap_weight_fraction":
                sum(eval_overlap[key] for key in matched_edges) / evaluation_weight
                if evaluation_weight else None,
        },
        "changed_pages_coaccess_vs_heat": sum(assignments["coaccess"][p] != assignments["heat"][p]
                                              for p in page_rank),
        "evaluation_overlap_edges_touching_changed_pages": len(touched),
        "evaluation_overlap_weight_touching_changed_pages": sum(x[0] for x in touched),
        "evaluation_edges_whose_same_bank_status_changes": len(affected),
        "evaluation_overlap_weight_whose_same_bank_status_changes": sum(x[0] for x in affected),
        "profile_scores": {name: score(profile_overlap, layout)
                           for name, layout in assignments.items()},
        "heldout_fixed_timeline_scores": {name: score(eval_overlap, layout)
                                           for name, layout in assignments.items()},
        "diagnostic_oracle_using_evaluation_overlap_not_deployable": {
            "score": score(eval_overlap, oracle_assignment),
            "changed_pages_vs_heat": sum(oracle_assignment[p] != assignments["heat"][p]
                                         for p in page_rank),
        },
        "shuffled_profile_edge_null": {
            "caveat": "NOT a matched 31-page ablation; shuffled construction may change many cold-page assignments",
            "count": len(null_scores), "seed": args.seed,
            "same_bank_overlap_mean": sum(null_scores) / len(null_scores) if null_scores else None,
            "same_bank_overlap_min": min(null_scores) if null_scores else None,
            "same_bank_overlap_max": max(null_scores) if null_scores else None,
            "fraction_null_at_least_as_good_as_coaccess":
                sum(x <= observed for x in null_scores) / len(null_scores) if null_scores else None,
            "changed_pages_mean": sum(null_changes) / len(null_changes) if null_changes else None,
            "changed_pages_min": min(null_changes) if null_changes else None,
            "changed_pages_max": max(null_changes) if null_changes else None,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

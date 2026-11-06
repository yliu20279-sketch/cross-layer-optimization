#!/usr/bin/env python3
"""Read-only mechanism diagnosis for a fixed-timeline coaccess transfer pair."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from derive_profile_assignments import load_profile, overlap_weights
from validate_coaccess_fixed_trace import read_layout


def edge_record(key, weight, other, heat, coaccess):
    rank, (a, b) = key
    heat_same = heat[a] == heat[b]
    co_same = coaccess[a] == coaccess[b]
    return {
        "rank": rank,
        "pages": [list(a), list(b)],
        "weight": weight,
        "other_trace_weight": other.get(key, 0.0),
        "heat_same_bank": heat_same,
        "coaccess_same_bank": co_same,
    }


def main():
    parser = argparse.ArgumentParser()
    for flag in ("profile-events", "evaluation-events", "heat-layout", "coaccess-layout"):
        parser.add_argument("--" + flag, required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    heat_layout, _ = read_layout(args.heat_layout)
    co_layout, _ = read_layout(args.coaccess_layout)
    if set(heat_layout) != set(co_layout):
        raise ValueError("layouts cover different pages")
    if any(heat_layout[p][0] != co_layout[p][0] for p in heat_layout):
        raise ValueError("rank placement differs")
    rank_by_page = {p: rank for p, (rank, _) in heat_layout.items()}
    heat_bank = {p: bank for p, (_, bank) in heat_layout.items()}
    co_bank = {p: bank for p, (_, bank) in co_layout.items()}
    profile_intervals, profile_reads = load_profile(args.profile_events, rank_by_page)
    eval_intervals, eval_reads = load_profile(args.evaluation_events, rank_by_page)
    profile = overlap_weights(profile_intervals)
    evaluation = overlap_weights(eval_intervals)
    changed = {p for p in rank_by_page if heat_bank[p] != co_bank[p]}
    matched = set(profile) & set(evaluation)
    profile_total = sum(profile.values())
    eval_total = sum(evaluation.values())

    layer = defaultdict(lambda: {"profile_edges": 0, "evaluation_edges": 0,
                                 "matched_evaluation_edges": 0,
                                 "profile_weight": 0.0, "evaluation_weight": 0.0,
                                 "matched_evaluation_weight": 0.0,
                                 "changed_pages": 0, "touched_evaluation_edges": 0,
                                 "touched_evaluation_weight": 0.0,
                                 "same_bank_status_changed_edges": 0,
                                 "same_bank_status_changed_weight": 0.0})
    for p in changed:
        layer[p[0]]["changed_pages"] += 1
    for key, weight in profile.items():
        a, b = key[1]
        for lid in {a[0], b[0]}:
            layer[lid]["profile_edges"] += 1
            layer[lid]["profile_weight"] += weight
    touched = []
    flipped = []
    for key, weight in evaluation.items():
        a, b = key[1]
        lids = {a[0], b[0]}
        for lid in lids:
            row = layer[lid]
            row["evaluation_edges"] += 1
            row["evaluation_weight"] += weight
            if key in matched:
                row["matched_evaluation_edges"] += 1
                row["matched_evaluation_weight"] += weight
        if a in changed or b in changed:
            touched.append(key)
            for lid in lids:
                layer[lid]["touched_evaluation_edges"] += 1
                layer[lid]["touched_evaluation_weight"] += weight
            if (heat_bank[a] == heat_bank[b]) != (co_bank[a] == co_bank[b]):
                flipped.append(key)
                for lid in lids:
                    layer[lid]["same_bank_status_changed_edges"] += 1
                    layer[lid]["same_bank_status_changed_weight"] += weight

    profile_pages = set(profile_reads)
    eval_pages = set(eval_reads)
    result = {
        "scope": "Observed fixed event timelines; no causality or end-to-end latency claim",
        "profile_overlap_edges": len(profile),
        "evaluation_overlap_edges": len(evaluation),
        "matched_edges": len(matched),
        "profile_overlap_weight": profile_total,
        "evaluation_overlap_weight": eval_total,
        "matched_profile_weight_fraction": sum(profile[k] for k in matched) / profile_total if profile_total else None,
        "matched_evaluation_weight_fraction": sum(evaluation[k] for k in matched) / eval_total if eval_total else None,
        "observed_page_overlap": {
            "profile_pages": len(profile_pages),
            "evaluation_pages": len(eval_pages),
            "shared_pages": len(profile_pages & eval_pages),
            "evaluation_read_fraction_on_profile_pages":
                sum(n for p, n in eval_reads.items() if p in profile_pages) / sum(eval_reads.values()),
        },
        "changed_pages": {
            "total": len(changed),
            "profile_observed": len(changed & profile_pages),
            "evaluation_observed": len(changed & eval_pages),
            "observed_in_both": len(changed & profile_pages & eval_pages),
            "evaluation_read_fraction_on_changed_pages":
                sum(n for p, n in eval_reads.items() if p in changed) / sum(eval_reads.values()),
        },
        "touched_evaluation_edges": len(touched),
        "touched_evaluation_weight_fraction": sum(evaluation[k] for k in touched) / eval_total if eval_total else None,
        "same_bank_status_changed_edges": len(flipped),
        "top_profile_edges": [edge_record(k, w, evaluation, heat_bank, co_bank)
                              for k, w in sorted(profile.items(), key=lambda x: -x[1])[:20]],
        "top_evaluation_edges": [edge_record(k, w, profile, heat_bank, co_bank)
                                 for k, w in sorted(evaluation.items(), key=lambda x: -x[1])[:20]],
        "touched_evaluation_edge_details": [edge_record(k, evaluation[k], profile, heat_bank, co_bank)
                                            for k in sorted(touched, key=lambda k: -evaluation[k])],
        "per_layer": {str(k): v for k, v in sorted(layer.items())},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items()
                      if k not in {"top_profile_edges", "top_evaluation_edges",
                                   "touched_evaluation_edge_details", "per_layer"}}, indent=2))


if __name__ == "__main__":
    main()

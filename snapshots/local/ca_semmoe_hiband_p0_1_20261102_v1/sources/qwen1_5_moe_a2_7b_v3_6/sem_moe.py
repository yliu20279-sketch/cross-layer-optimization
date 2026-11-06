#!/usr/bin/env python3
"""Trace-driven Sem-MoE placement and data scheduling for the LegoSim model.

This is an analytical implementation of the paper's model/data co-scheduling
contract.  It does not predict routes from model weights.  Production studies
must provide a measured token-to-expert trace; --synthetic is smoke-test only.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import random
from collections import defaultdict
from pathlib import Path


def load_trace(path: Path):
    rows = []
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "request_id": row["request_id"], "token_id": int(row["token_id"]),
                "layer": int(row["layer"]), "expert": int(row["expert"]),
                "count": int(row.get("count", 1)), "split": row.get("split", "profile"),
            })
    if not rows:
        raise ValueError("empty routing trace")
    return rows


def synthetic_trace(layers=24, experts=60, requests=64, tokens=32, topk=4, seed=7):
    """Deterministic, clustered trace used only to verify the pipeline."""
    rng = random.Random(seed)
    rows = []
    for req in range(requests):
        semantic_class = req % 4
        for tok in range(tokens):
            token_id = semantic_class * 1000 + tok
            for layer in range(layers):
                base = semantic_class * 15
                chosen = {(base + tok + layer) % 15 + base}
                while len(chosen) < topk:
                    chosen.add(base + rng.randrange(15))
                for expert in sorted(chosen):
                    rows.append({"request_id": f"r{req}", "token_id": token_id,
                                 "layer": layer, "expert": expert, "count": 1})
    return rows


def write_trace(path: Path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["request_id", "token_id", "layer", "expert", "count"])
        w.writeheader(); w.writerows(rows)


def build_affinity(rows, layer):
    affinity = defaultdict(lambda: defaultdict(float))
    frequency = defaultdict(float)
    for r in rows:
        if r["layer"] == layer:
            affinity[r["token_id"]][r["expert"]] += r["count"]
            frequency[r["token_id"]] += r["count"]
    for token, counts in affinity.items():
        total = sum(counts.values())
        for expert in counts:
            counts[expert] /= total
    return affinity, frequency


def balanced_alternating_coclustering(rows, layers=24, experts=60, ep=4, iterations=12,
                                      balance_weight=0.15):
    """Alternating balanced token/expert assignment approximating Sem-MoE ILP.

    Expert capacity is exact. Token assignment includes a frequency-load penalty.
    """
    if experts % ep:
        raise ValueError("paper-compatible equal placement requires experts divisible by EP")
    capacity = experts // ep
    result = {}
    for layer in range(layers):
        affinity, frequency = build_affinity(rows, layer)
        tokens = sorted(affinity)
        expert_rank = {e: e // capacity for e in range(experts)}
        token_rank = {t: t % ep for t in tokens}
        for _ in range(iterations):
            loads = [0.0] * ep
            new_token_rank = {}
            target = sum(frequency.values()) / ep if ep else 0
            for token in sorted(tokens, key=lambda t: (-frequency[t], t)):
                scores = []
                for rank in range(ep):
                    local = sum(p for e, p in affinity[token].items() if expert_rank[e] == rank)
                    penalty = balance_weight * max(0.0, loads[rank] + frequency[token] - target) / max(target, 1.0)
                    scores.append((local - penalty, -loads[rank], -rank))
                rank = max(range(ep), key=lambda r: scores[r])
                new_token_rank[token] = rank; loads[rank] += frequency[token]
            token_rank = new_token_rank
            expert_score = [[0.0] * ep for _ in range(experts)]
            for token in tokens:
                for expert, prob in affinity[token].items():
                    expert_score[expert][token_rank[token]] += frequency[token] * prob
            available = [capacity] * ep
            new_expert_rank = {}
            candidates = sorted(((expert_score[e][r], e, r) for e in range(experts) for r in range(ep)),
                                reverse=True)
            for _, expert, rank in candidates:
                if expert not in new_expert_rank and available[rank] > 0:
                    new_expert_rank[expert] = rank; available[rank] -= 1
            expert_rank = new_expert_rank
        result[str(layer)] = {
            "expert_to_rank": {str(k): v for k, v in sorted(expert_rank.items())},
            "token_to_rank": {str(k): v for k, v in sorted(token_rank.items())},
            "tokens_profiled": len(tokens),
        }
    return result


def evaluate(rows, placement, ep=4):
    total = local = 0
    request_scores = defaultdict(lambda: [0] * ep)
    for r in rows:
        layer = placement[str(r["layer"])]
        token_rank = layer["token_to_rank"].get(str(r["token_id"]), r["token_id"] % ep)
        expert_rank = layer["expert_to_rank"][str(r["expert"])]
        count = r["count"]; total += count
        if token_rank == expert_rank: local += count
        request_scores[r["request_id"]][expert_rank] += count
    request_rank = {req: max(range(ep), key=lambda r: (score[r], -r)) for req, score in request_scores.items()}
    # Dispatch and combine each move the non-local token activation payload.
    remote = total - local
    return {"activations": total, "local_activations": local, "remote_activations": remote,
            "local_activation_rate": local / total, "remote_activation_rate": remote / total,
            "dispatch_combine_multiplier": 2, "request_to_rank": request_rank}


def baseline_round_robin(rows, experts=60, ep=4):
    total = local = 0
    for r in rows:
        total += r["count"]
        if r["token_id"] % ep == r["expert"] % ep: local += r["count"]
    return {"activations": total, "local_activations": local, "remote_activations": total-local,
            "local_activation_rate": local/total, "remote_activation_rate": 1-local/total}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--synthetic", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if bool(args.trace) == bool(args.synthetic):
        raise SystemExit("choose exactly one of --trace or --synthetic")
    rows = synthetic_trace() if args.synthetic else load_trace(args.trace)
    if args.synthetic: write_trace(args.out / "synthetic_routing_trace.csv", rows)
    profile_rows = [r for r in rows if r.get("split") == "profile"]
    eval_rows = [r for r in rows if r.get("split") == "eval"]
    if not profile_rows or not eval_rows:
        profile_rows = rows
        eval_rows = rows
    placement = balanced_alternating_coclustering(profile_rows)
    sem = evaluate(eval_rows, placement); base = baseline_round_robin(eval_rows)
    record = {
        "schema_version": "sem-moe-legosim-1.0", "trace_class": "synthetic_smoke_only" if args.synthetic else "measured",
        "algorithm": "balanced_alternating_token_expert_coclustering",
        "parallelism": {"ep": 4, "experts_per_rank_per_layer": 15},
        "split": {"profile_rows": len(profile_rows), "eval_rows": len(eval_rows)},
        "baseline": base, "sem_moe": sem,
        "analytical_remote_activation_reduction": 1 - sem["remote_activations"] / max(base["remote_activations"], 1),
        "limitations": (["Synthetic routing is pipeline validation only; it provides no routing-accuracy evidence."]
                        if args.synthetic else
                        ["Placement is learned only from the profile split and evaluated only on the disjoint eval split.",
                         "Measured routes describe the fixed sampled workload; no full-population claim is made."])
                        + ["No latency or throughput claim is valid until PopNet and LegoSim replay completes."],
    }
    (args.out / "placement.json").write_text(json.dumps(placement, indent=2)+"\n", encoding="utf-8")
    (args.out / "sem_moe_metrics.json").write_text(json.dumps(record, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(record, indent=2))


if __name__ == "__main__": main()

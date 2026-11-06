#!/usr/bin/env python3
"""Build trace-driven concurrency graphs for four HiBand/Sem-MoE schemes."""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

H = 2048
TOKEN_BYTES = H * 2
LAYERS = 24
EP = 4
WORKING_SET_PER_RANK = 4 * 1024 * 1024
SLOT_BYTES = 4 * 1024 * 1024
FIELDS = ["id", "kind", "task", "phase", "pe", "bytes", "sample_bytes", "address",
          "cycles", "src", "dst", "scope", "rank"]
MODES = [("FULL_LOCAL", 1536, 0), ("LOCAL_BIAS", 1024, 512),
         ("GLOBAL_BIAS", 512, 1024), ("FULL_GLOBAL", 0, 1536)]
SCHEMES = ("baseline_ep", "hiband", "sem_moe", "hiband_sem_moe")


def write_csv(path: Path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def load_trace(path: Path):
    requests = []
    seen = set()
    data = defaultdict(Counter)
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["split"] != "eval":
                continue
            req = row["request_id"]
            if req not in seen:
                seen.add(req); requests.append(req)
            data[(req, int(row["layer"]))][(int(row["token_id"]), int(row["expert"]))] += 1
    return requests, data


def rank_maps(placement, semantic):
    expert_rank = {}
    token_rank = {}
    for layer in range(LAYERS):
        if semantic:
            p = placement[str(layer)]
            expert_rank[layer] = {int(k): int(v) for k, v in p["expert_to_rank"].items()}
            token_rank[layer] = {int(k): int(v) for k, v in p["token_to_rank"].items()}
        else:
            expert_rank[layer] = {e: e % EP for e in range(60)}
            token_rank[layer] = {}
    return expert_rank, token_rank


def build_graph(out: Path, scheme: str, selected: list[str], trace, placement):
    semantic = scheme in ("sem_moe", "hiband_sem_moe")
    expert_rank, token_rank = rank_maps(placement, semantic)
    ops, deps = [], []

    def op(kind, task, phase, pe, bytes_=0, sample=0, address=0, cycles=0,
           src=-1, dst=-1, scope="local", rank=0):
        idx = len(ops)
        ops.append(dict(id=idx, kind=kind, task=task, phase=phase, pe=pe, bytes=int(bytes_),
                        sample_bytes=int(sample), address=int(address), cycles=int(cycles),
                        src=src, dst=dst, scope=scope, rank=rank))
        return idx

    def dep(src, dst):
        deps.append({"src": src, "dst": dst})

    request_tails = {}
    remote_activations = total_activations = 0
    for request_slot, req in enumerate(selected):
        tail = None
        for layer in range(LAYERS):
            stage = layer // 6
            routers = []
            for src_rank in range(EP):
                pe = stage * 4 + src_rank
                attention = op("COMPUTE", f"R{request_slot}_L{layer}_attention", "COMPUTE", pe,
                               cycles=640 * 4096 // EP, rank=src_rank)
                if tail is not None: dep(tail, attention)
                router = op("COMPUTE", f"R{request_slot}_L{layer}_router", "COMPUTE", pe,
                            cycles=640 * 60 // EP, rank=src_rank)
                dep(attention, router); routers.append(router)
            route_barrier = op("CPU", f"R{request_slot}_L{layer}_route_ready", scheme, stage * 4)
            for router in routers: dep(router, route_barrier)

            flows = Counter()
            expert_hits = Counter()
            for (token, expert), count in trace[(req, layer)].items():
                src_rank = token_rank[layer].get(token, token % EP)
                dst_rank = expert_rank[layer][expert]
                flows[(src_rank, dst_rank)] += count
                expert_hits[(dst_rank, expert)] += count
                total_activations += count
                remote_activations += count * (src_rank != dst_rank)

            dispatch_to_dst = defaultdict(list)
            for (src_rank, dst_rank), count in sorted(flows.items()):
                if src_rank == dst_rank: continue
                src_pe, dst_pe = stage * 4 + src_rank, stage * 4 + dst_rank
                net = op("NET", f"R{request_slot}_L{layer}_dispatch_{src_rank}_{dst_rank}", scheme,
                         src_pe, count * TOKEN_BYTES, src=src_pe, dst=dst_pe,
                         scope="global", rank=src_rank)
                dep(route_barrier, net); dispatch_to_dst[dst_rank].append(net)

            expert_tails = []
            active_by_rank = defaultdict(list)
            for (dst_rank, expert), count in expert_hits.items():
                active_by_rank[dst_rank].append((expert, count))
            for dst_rank in range(EP):
                arrival = op("CPU", f"R{request_slot}_L{layer}_rank{dst_rank}_arrive", scheme,
                             stage * 4 + dst_rank, rank=dst_rank)
                dep(route_barrier, arrival)
                for net in dispatch_to_dst[dst_rank]: dep(net, arrival)
                hits = active_by_rank[dst_rank]
                hit_total = sum(c for _, c in hits) or 1
                rank_tails = []
                for expert, count in sorted(hits):
                    local_slot = sorted(e for e, r in expert_rank[layer].items() if r == dst_rank).index(expert)
                    represented = max(256, round(WORKING_SET_PER_RANK * count / hit_total / 256) * 256)
                    sample = min(represented, max(256, min(2048, count * 32)))
                    address = (layer % 6) * 64 * 1024 * 1024 + local_slot * SLOT_BYTES
                    load = op("LOAD", f"R{request_slot}_L{layer}_E{expert}_weights", scheme,
                              stage * 4 + dst_rank, represented, sample, address, rank=dst_rank)
                    dep(arrival, load)
                    compute = op("COMPUTE", f"R{request_slot}_L{layer}_E{expert}_compute", "COMPUTE",
                                 stage * 4 + dst_rank,
                                 cycles=max(1, count * 3 * H * 1408 // (256 * 256)), rank=dst_rank)
                    dep(load, compute); rank_tails.append(compute)
                rank_done = op("CPU", f"R{request_slot}_L{layer}_rank{dst_rank}_experts_done", scheme,
                               stage * 4 + dst_rank, rank=dst_rank)
                for x in rank_tails or [arrival]: dep(x, rank_done)
                expert_tails.append(rank_done)

            combines = []
            for (src_rank, dst_rank), count in sorted(flows.items()):
                if src_rank == dst_rank: continue
                src_pe, dst_pe = stage * 4 + dst_rank, stage * 4 + src_rank
                net = op("NET", f"R{request_slot}_L{layer}_combine_{dst_rank}_{src_rank}", scheme,
                         src_pe, count * TOKEN_BYTES, src=src_pe, dst=dst_pe,
                         scope="global", rank=dst_rank)
                dep(expert_tails[dst_rank], net); combines.append(net)
            layer_done = op("CPU", f"R{request_slot}_L{layer}_done", scheme, stage * 4)
            for x in expert_tails + combines: dep(x, layer_done)
            tail = layer_done
        request_tails[req] = tail

    finish = op("BARRIER", "finish", scheme, 0)
    for tail in request_tails.values(): dep(tail, finish)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "ops.csv", ops, FIELDS)
    write_csv(out / "deps.csv", deps, ["src", "dst"])
    write_csv(out / "modes.csv", ({"mode": m, "local_bytes_per_cycle": l,
                                    "global_bytes_per_cycle": g} for m, l, g in MODES),
              ["mode", "local_bytes_per_cycle", "global_bytes_per_cycle"])
    manifest = {
        "schema_version": "qwen1.5-moe-scale-graph-1.0", "scheme": scheme,
        "concurrency": len(selected), "request_ids": selected,
        "operations": len(ops), "dependencies": len(deps),
        "total_activations": total_activations, "remote_activations": remote_activations,
        "remote_activation_rate": remote_activations / total_activations,
        "memory_contract": "4 MiB represented active expert working set per rank/layer/request, split by measured expert hits",
        "memory_contract_basis": "ceil(2.7B activated parameters * 0.5 byte INT4 / 24 layers / 16 partitions) = 4 MiB",
        "sample_contract": "256..2048 bytes per expert op, proportional to measured hits; sampled Ramulator only",
    }
    (out / "graph_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def build_batched_graph(out: Path, scheme: str, selected: list[str], trace, placement):
    """Build one continuous-batch stream; weights are shared across requests."""
    semantic = scheme in ("sem_moe", "hiband_sem_moe")
    expert_rank, token_rank = rank_maps(placement, semantic)
    ops, deps = [], []

    def op(kind, task, phase, pe, bytes_=0, sample=0, address=0, cycles=0,
           src=-1, dst=-1, scope="local", rank=0):
        idx = len(ops)
        ops.append(dict(id=idx, kind=kind, task=task, phase=phase, pe=pe, bytes=int(bytes_),
                        sample_bytes=int(sample), address=int(address), cycles=int(cycles),
                        src=src, dst=dst, scope=scope, rank=rank))
        return idx

    def dep(src, dst): deps.append({"src": src, "dst": dst})

    tail = None
    remote_activations = total_activations = 0
    batch = len(selected)
    for layer in range(LAYERS):
        stage = layer // 6
        routers = []
        for src_rank in range(EP):
            pe = stage * 4 + src_rank
            attention = op("COMPUTE", f"L{layer}_batched_attention", "COMPUTE", pe,
                           cycles=batch * 640 * 4096 // EP, rank=src_rank)
            if tail is not None: dep(tail, attention)
            router = op("COMPUTE", f"L{layer}_batched_router", "COMPUTE", pe,
                        cycles=batch * 640 * 60 // EP, rank=src_rank)
            dep(attention, router); routers.append(router)
        route_barrier = op("CPU", f"L{layer}_route_ready", scheme, stage * 4)
        for router in routers: dep(router, route_barrier)

        flows, expert_hits = Counter(), Counter()
        for req in selected:
            for (token, expert), count in trace[(req, layer)].items():
                src_rank = token_rank[layer].get(token, token % EP)
                dst_rank = expert_rank[layer][expert]
                flows[(src_rank, dst_rank)] += count
                expert_hits[(dst_rank, expert)] += count
                total_activations += count
                remote_activations += count * (src_rank != dst_rank)

        dispatch_to_dst = defaultdict(list)
        for (src_rank, dst_rank), count in sorted(flows.items()):
            if src_rank == dst_rank: continue
            src_pe, dst_pe = stage * 4 + src_rank, stage * 4 + dst_rank
            net = op("NET", f"L{layer}_dispatch_{src_rank}_{dst_rank}", scheme, src_pe,
                     count * TOKEN_BYTES, src=src_pe, dst=dst_pe, scope="global", rank=src_rank)
            dep(route_barrier, net); dispatch_to_dst[dst_rank].append(net)

        active_by_rank = defaultdict(list)
        for (dst_rank, expert), count in expert_hits.items():
            active_by_rank[dst_rank].append((expert, count))
        expert_tails = []
        for dst_rank in range(EP):
            arrival = op("CPU", f"L{layer}_rank{dst_rank}_arrive", scheme,
                         stage * 4 + dst_rank, rank=dst_rank)
            dep(route_barrier, arrival)
            for net in dispatch_to_dst[dst_rank]: dep(net, arrival)
            hits = active_by_rank[dst_rank]
            hit_total = sum(c for _, c in hits) or 1
            rank_tails = []
            local_experts = sorted(e for e, r in expert_rank[layer].items() if r == dst_rank)
            for expert, count in sorted(hits):
                local_slot = local_experts.index(expert)
                weight_share = round(WORKING_SET_PER_RANK * count / hit_total / 256) * 256
                activation_bytes = count * TOKEN_BYTES
                represented = max(256, weight_share + activation_bytes)
                # More requests increase sampled controller pressure while the
                # shared batched weight working set remains fixed.
                sample = min(represented, max(256, min(65536, count * 32)))
                address = (layer % 6) * 64 * 1024 * 1024 + local_slot * SLOT_BYTES
                load = op("LOAD", f"L{layer}_E{expert}_batched_weights", scheme,
                          stage * 4 + dst_rank, represented, sample, address, rank=dst_rank)
                dep(arrival, load)
                compute = op("COMPUTE", f"L{layer}_E{expert}_batched_compute", "COMPUTE",
                             stage * 4 + dst_rank,
                             cycles=max(1, count * 3 * H * 1408 // (256 * 256)), rank=dst_rank)
                dep(load, compute); rank_tails.append(compute)
            rank_done = op("CPU", f"L{layer}_rank{dst_rank}_experts_done", scheme,
                           stage * 4 + dst_rank, rank=dst_rank)
            for x in rank_tails or [arrival]: dep(x, rank_done)
            expert_tails.append(rank_done)

        combines = []
        for (src_rank, dst_rank), count in sorted(flows.items()):
            if src_rank == dst_rank: continue
            src_pe, dst_pe = stage * 4 + dst_rank, stage * 4 + src_rank
            net = op("NET", f"L{layer}_combine_{dst_rank}_{src_rank}", scheme, src_pe,
                     count * TOKEN_BYTES, src=src_pe, dst=dst_pe, scope="global", rank=dst_rank)
            dep(expert_tails[dst_rank], net); combines.append(net)
        layer_done = op("CPU", f"L{layer}_done", scheme, stage * 4)
        for x in expert_tails + combines: dep(x, layer_done)
        tail = layer_done

    finish = op("BARRIER", "finish", scheme, 0); dep(tail, finish)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "ops.csv", ops, FIELDS); write_csv(out / "deps.csv", deps, ["src", "dst"])
    write_csv(out / "modes.csv", ({"mode": m, "local_bytes_per_cycle": l,
                                    "global_bytes_per_cycle": g} for m, l, g in MODES),
              ["mode", "local_bytes_per_cycle", "global_bytes_per_cycle"])
    manifest = {
        "schema_version": "qwen1.5-moe-scale-graph-1.1", "batching": "continuous_batch",
        "scheme": scheme, "concurrency": batch, "request_ids": selected,
        "operations": len(ops), "dependencies": len(deps),
        "total_activations": total_activations, "remote_activations": remote_activations,
        "remote_activation_rate": remote_activations / total_activations,
        "memory_contract": "4 MiB shared active-expert weights per rank/layer/batch plus 4096 bytes per routed activation, split by measured hits",
        "memory_contract_basis": "ceil(2.7B activated parameters * 0.5 byte INT4 / 24 layers / 16 partitions) = 4 MiB",
        "sample_contract": "256..65536 bytes per expert op proportional to measured hit count",
    }
    (out / "graph_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", type=Path, required=True)
    ap.add_argument("--placement", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--concurrency", default="1,2,4,8,16")
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args()
    requests, trace = load_trace(args.trace)
    placement = json.loads(args.placement.read_text())
    concurrencies = [int(x) for x in args.concurrency.split(",")]
    all_runs = []
    for repeat in range(args.repeats):
        for concurrency in concurrencies:
            start = repeat * max(concurrencies)
            selected = [requests[(start + i) % len(requests)] for i in range(concurrency)]
            for scheme in SCHEMES:
                graph = args.out / f"c{concurrency}" / f"rep{repeat + 1}" / scheme
                all_runs.append(build_batched_graph(graph, scheme, selected, trace, placement))
    (args.out / "matrix_manifest.json").write_text(json.dumps({"runs": all_runs}, indent=2) + "\n")
    print(json.dumps({"graphs": len(all_runs), "eval_requests": len(requests)}, indent=2))


if __name__ == "__main__":
    main()

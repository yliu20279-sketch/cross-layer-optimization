#!/usr/bin/env python3
"""Export actual and ideal-balanced per-op cycles from official DeepStack."""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deepstack-root", type=Path, required=True)
    ap.add_argument("--ops", type=Path, required=True)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    cfg = json.loads(args.config.read_text())
    root = args.deepstack_root.resolve()
    sys.path[:0] = [str(root / "src/deepstack"), str(root / "src/tilesight"), str(root)]
    from bank_oracle.engine import apply_littles_law_cycles, service_requests
    from bank_oracle.layout import BankSwizzle
    from bank_oracle.spec import DramBankSpec

    assert (root / "SOURCE_COMMIT").read_text().strip() == cfg["official_commit"]
    fields = (
        "total_layers", "connected_layers", "banks_per_layer", "row_bytes",
        "sector_bytes", "sector_cycles", "recharge_cycles", "data_rate_hz",
        "round_trip_latency_cycles", "latency_clock_hz",
    )
    spec = DramBankSpec(**{key: cfg[key] for key in fields})
    swizzle = BankSwizzle(**cfg.get("bank_swizzle", {}))
    npu_hz = 1e9
    groups = defaultdict(list)
    with args.ops.open(newline="") as src:
        for row in csv.DictReader(src):
            if row["kind"] not in ("LOAD", "STORE"):
                continue
            match = re.match(r"S(\d+)L(\d+)W(\d+)", row["task"])
            if not match:
                raise RuntimeError(f"memory task lacks step/layer/wave prefix: {row['task']}")
            groups[(int(match.group(1)), int(match.group(2)), int(match.group(3)), int(row["pe"]))].append(row)

    per_op = {}
    group_audit = []
    for key, rows in sorted(groups.items()):
        requests = []
        represented = sampled = 0
        for row in rows:
            address, sample = int(row["address"]), int(row["sample_bytes"])
            if sample <= 0:
                raise RuntimeError("memory op lacks a positive stratified sample")
            lo = address // spec.sector_bytes
            hi = (address + sample + spec.sector_bytes - 1) // spec.sector_bytes
            requests.append(np.arange(lo, hi, dtype=np.int64))
            represented += int(row["bytes"])
            sampled += sample
        result = service_requests(
            requests, spec, connectivity=cfg["connectivity"],
            swizzle=swizzle, coalesce_scope=cfg["coalesce_scope"],
        )
        scale = represented / sampled
        actual, _, _ = apply_littles_law_cycles(
            result.cycles * scale, represented,
            cfg["outstanding_bytes_per_partition"], spec,
        )
        ideal, _, _ = apply_littles_law_cycles(
            result.sector_lower_bound_cycles * scale, represented,
            cfg["outstanding_bytes_per_partition"], spec,
        )
        actual_npu = math.ceil(actual * npu_hz / spec.data_rate_hz)
        ideal_npu = math.ceil(ideal * npu_hz / spec.data_rate_hz)
        if ideal_npu > actual_npu:
            raise RuntimeError("DeepStack lower bound exceeds actual wave service")

        def apportion(total: int) -> dict[int, int]:
            raw = [(int(r["id"]), total * int(r["bytes"]) / represented) for r in rows]
            out = {op_id: math.floor(value) for op_id, value in raw}
            remainder = total - sum(out.values())
            order = sorted(raw, key=lambda item: (-(item[1] - math.floor(item[1])), item[0]))
            for op_id, _ in order[:remainder]:
                out[op_id] += 1
            return out

        ideal_parts = apportion(ideal_npu)
        penalty_parts = apportion(actual_npu - ideal_npu)
        for row in rows:
            op_id = int(row["id"])
            per_op[op_id] = (ideal_parts[op_id] + penalty_parts[op_id], ideal_parts[op_id], penalty_parts[op_id])
        group_audit.append({
            "step": key[0], "layer": key[1], "wave": key[2], "partition": key[3], "ops": len(rows),
            "represented_bytes": represented, "sampled_bytes": sampled,
            "sample_scale": scale, "actual_cycles_npu": actual_npu,
            "ideal_balanced_cycles_npu": ideal_npu,
            "bank_mapping_row_penalty_cycles_npu": actual_npu - ideal_npu,
        })

    with args.output.open("w", newline="") as dst:
        writer = csv.writer(dst)
        writer.writerow([
            "op_id", "actual_cycles_npu", "ideal_balanced_cycles_npu",
            "bank_mapping_row_penalty_cycles_npu",
        ])
        for op_id in sorted(per_op):
            writer.writerow([op_id, *per_op[op_id]])
    audit_path = args.output.with_name("deepstack_wave_audit.json")
    audit_path.write_text(json.dumps(group_audit, indent=2) + "\n")
    print(json.dumps({
        "status": "PASS", "memory_ops": len(per_op), "waves": len(groups), "output": str(args.output),
        "official_commit": cfg["official_commit"], "bank_swizzle": cfg.get("bank_swizzle", {"kind": "none"}),
        "definition": "step-layer-wave-partition joint stratified-sample groups; official actual minus sector-parallel lower bound; both extrapolated by represented/sample bytes before identical Little's-law floor",
    }))


if __name__ == "__main__":
    main()

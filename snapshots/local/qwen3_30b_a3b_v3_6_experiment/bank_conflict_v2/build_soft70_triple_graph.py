#!/usr/bin/env python3
"""Build the c4 soft70 optimization graph with 50% memory compression.

The static XOR is deliberately implemented in the DRAM address mapper after
the soft70 stress mapping, not by rewriting the pre-mapping graph addresses.
"""
import csv
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "results/bank_memory_stress_full48_co_scale_strict_v2/graphs/c4_co"
DST = ROOT / "results/bank_soft70_triple_v1/graph_c4_ratio50"


def read_csv(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def compressed_size(value):
    value = int(value)
    return max(256, ((value + 1) // 2 + 255) // 256 * 256)


def main():
    DST.mkdir(parents=True, exist_ok=True)
    ops = read_csv(SRC / "ops.csv")
    addresses = read_csv(SRC / "address_manifest.csv")
    address_by_id = {int(row["op_id"]): row for row in addresses}
    original_bytes = 0
    compressed_bytes = 0
    memory_ops = 0
    for op in ops:
        if op["kind"] not in ("LOAD", "STORE"):
            continue
        memory_ops += 1
        original_bytes += int(op["bytes"])
        new_bytes = compressed_size(op["bytes"])
        new_sample = min(new_bytes, compressed_size(op["sample_bytes"]))
        op["bytes"] = str(new_bytes)
        op["sample_bytes"] = str(new_sample)
        address = address_by_id[int(op["id"])]
        address["bytes"] = str(new_bytes)
        address["sample_bytes"] = str(new_sample)
        compressed_bytes += new_bytes
    write_csv(DST / "ops.csv", ops)
    write_csv(DST / "address_manifest.csv", addresses)
    for name in ("deps.csv", "modes.csv", "memory_stress_manifest.json"):
        shutil.copy2(SRC / name, DST / name)
    manifest = json.loads((SRC / "graph_manifest.json").read_text())
    manifest.update({
        "scheme": "soft70_ratio50_then_static_xor_then_hotlink",
        "compression_target": 0.5,
        "compression_actual": compressed_bytes / original_bytes,
        "xor_order": "soft70 mapping then Bank XOR RowLow",
        "xor_encoding": "mapped Bank XOR byte-address RowLow[21:18]",
        "hotlink_policy": {"threshold_bytes": 524288, "multiplier": 1.5, "setup_cycles": 10000},
        "decoder_cost_model": "offline fixed-order replay at 128 B/cycle",
        "classification": "controlled soft70 Bank-hotspot address-mapping stress; not a natural Qwen3 workload",
    })
    (DST / "graph_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "memory_ops": memory_ops,
                      "original_bytes": original_bytes,
                      "compressed_bytes": compressed_bytes,
                      "actual_ratio": compressed_bytes / original_bytes}, indent=2))


if __name__ == "__main__":
    main()

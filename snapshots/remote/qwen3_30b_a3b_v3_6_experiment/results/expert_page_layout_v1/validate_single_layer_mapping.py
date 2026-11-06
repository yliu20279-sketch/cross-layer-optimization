#!/usr/bin/env python3
"""Check every tagged DRAM request against a functional page layout."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


TX = 256
COLUMNS = 64


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--layout", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    with args.layout.open(newline="") as handle:
        layout = {int(row["op_id"]): row for row in csv.DictReader(handle)}
    checked = 0
    per_op = defaultdict(Counter)
    decoded_addresses = {}
    with (args.run / "bank_requests.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            op_id = int(row["op_id"])
            if op_id not in layout:
                continue
            expected = layout[op_id]
            offset = int(row["address"]) - int(expected["address_base"])
            assert 0 <= offset < int(expected["page_bytes"])
            tx_index = offset // TX
            bank = int(row["bankgroup"]) * 4 + int(row["bank"])
            expected_row = int(expected["row_base"]) + tx_index // COLUMNS
            expected_col = tx_index % COLUMNS
            assert bank == int(expected["bank"]), (op_id, bank, expected["bank"])
            assert int(row["row"]) == expected_row, (op_id, row["row"], expected_row)
            assert int(row["column"]) == expected_col, (op_id, row["column"], expected_col)
            physical = (int(row["partition"]), bank, expected_row, expected_col)
            original = int(row["address"])
            prior = decoded_addresses.setdefault(physical, original)
            assert prior == original, (physical, prior, original)
            per_op[op_id]["transactions"] += 1
            per_op[op_id]["wait_ticks"] += int(row["cross_request_bank_wait_ticks"])
            checked += 1
    assert checked > 0
    assert set(per_op) == set(layout)
    base = json.loads((args.baseline / "run_manifest.json").read_text())
    mapped = json.loads((args.run / "run_manifest.json").read_text())
    for key in ("operations", "dependencies", "represented_mem_bytes", "sampled_mem_bytes",
                "represented_remote_noc_bytes", "packets_injected", "packets_completed"):
        assert base[key] == mapped[key], (key, base[key], mapped[key])
    result = {
        "status": "PASS",
        "checked_expert_transactions": checked,
        "unique_decoded_addresses": len(decoded_addresses),
        "tagged_ops": len(layout),
        "all_tagged_transactions_match_bank_row_column": True,
        "conserved_manifest_fields": ["operations", "dependencies", "represented_mem_bytes",
                                      "sampled_mem_bytes", "represented_remote_noc_bytes",
                                      "packets_injected", "packets_completed"],
        "baseline_cycles": base["total_cycles"],
        "mapped_cycles": mapped["total_cycles"],
        "limit": "Single-layer mechanism validation; physical capacity of all resident pages is not established.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Validate every detailed DRAM transaction in a paging-inclusive layer run."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


TX = 256
COLUMNS = 64
EXPERT_ROW_START = 4096


def read_csv(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--layout", required=True, type=Path)
    parser.add_argument("--control", required=True, type=Path)
    parser.add_argument("--mapped", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    layout = {int(row["op_id"]): row for row in read_csv(args.layout)}
    ops = {int(row["id"]): row for row in read_csv(args.graph / "ops.csv")}
    addresses = {int(row["op_id"]): row for row in read_csv(args.graph / "address_manifest.csv")}
    graph = json.loads((args.graph / "graph_manifest.json").read_text())
    assert graph["bank_aware_pager"] and graph["misses"] > 0
    assert graph["peak_resident_pages_per_bank"] <= graph["per_bank_page_capacity"]
    tagged = defaultdict(set)
    counts = Counter()
    untagged_max_row = -1
    with (args.mapped / "bank_requests.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            op_id = int(row["op_id"])
            bank = int(row["bankgroup"]) * 4 + int(row["bank"])
            actual_row = int(row["row"])
            if op_id not in layout:
                untagged_max_row = max(untagged_max_row, actual_row)
                if actual_row >= EXPERT_ROW_START:
                    raise AssertionError(("untagged row overlap", op_id, actual_row))
                continue
            expected = layout[op_id]
            offset = int(row["address"]) - int(expected["address_base"])
            if not 0 <= offset < int(expected["page_bytes"]) or offset % TX:
                raise AssertionError(("bad offset", op_id, offset))
            tx_index = offset // TX
            expected_row = int(expected["row_base"]) + tx_index // COLUMNS
            expected_col = tx_index % COLUMNS
            if (bank, actual_row, int(row["column"])) != (
                int(expected["bank"]), expected_row, expected_col
            ):
                raise AssertionError(("decoded mismatch", op_id, tx_index))
            if int(row["partition"]) != int(addresses[op_id]["partition"]):
                raise AssertionError(("partition mismatch", op_id))
            if tx_index in tagged[op_id]:
                raise AssertionError(("duplicate transaction", op_id, tx_index))
            tagged[op_id].add(tx_index)
            counts[op_id] += 1
    if set(tagged) != set(layout):
        raise AssertionError("not all tagged operations appeared")
    for op_id in layout:
        expected_count = int(ops[op_id]["sample_bytes"]) // TX
        if tagged[op_id] != set(range(expected_count)):
            raise AssertionError(("incomplete transaction range", op_id, len(tagged[op_id]), expected_count))
    control = json.loads((args.control / "run_manifest.json").read_text())
    mapped = json.loads((args.mapped / "run_manifest.json").read_text())
    conserved = (
        "operations", "dependencies", "represented_mem_bytes", "sampled_mem_bytes",
        "represented_remote_noc_bytes", "packets_injected", "packets_completed"
    )
    if control["status"] != "PASS" or mapped["status"] != "PASS":
        raise AssertionError("non-PASS run")
    for key in conserved:
        if control[key] != mapped[key]:
            raise AssertionError(("conservation", key, control[key], mapped[key]))
    result = {
        "status": "PASS", "graph_misses": graph["misses"],
        "graph_evictions": graph["evictions"],
        "peak_resident_pages_per_bank": graph["peak_resident_pages_per_bank"],
        "per_bank_page_capacity": graph["per_bank_page_capacity"],
        "tagged_ops": len(layout), "checked_tagged_transactions": sum(counts.values()),
        "all_tagged_bank_row_column_offsets_valid": True,
        "all_tagged_transaction_ranges_complete": True,
        "max_untagged_decoded_row": untagged_max_row,
        "reserved_expert_row_start": EXPERT_ROW_START,
        "conserved_fields": conserved,
        "control_cycles": control["total_cycles"],
        "mapped_cycles": mapped["total_cycles"],
        "limitation": "one paging-inclusive layer; complete full48 detailed requests were not logged",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

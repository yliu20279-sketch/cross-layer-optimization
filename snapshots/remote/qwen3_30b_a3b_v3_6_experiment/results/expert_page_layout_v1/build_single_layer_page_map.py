#!/usr/bin/env python3
"""Functional Bank-placement map for one layer without page faults.

This verifies that a page identity survives the frontend and address mapper.
It is deliberately not a capacity-feasible full-model placement algorithm.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path


PAGE = 2_359_296
TX = 256
# LPDDR5 organization has 1024 columns and internal prefetch 16; the
# Ramulator address mapper therefore decodes 64 transaction columns per row.
COLUMNS = 64
ROWS_PER_PAGE = math.ceil(PAGE / (TX * COLUMNS))
EXPERT = re.compile(r"^S\d+L(?P<layer>\d+)W\d+E(?P<expert>\d+)_weight_read$")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--policy", choices=("all_bank0", "round_robin"), required=True)
    args = parser.parse_args()
    graph_manifest = json.loads((args.graph / "graph_manifest.json").read_text())
    if graph_manifest["layers"] != 1 or graph_manifest["misses"] != 0:
        raise ValueError("functional map requires one layer and zero page faults")
    with (args.graph / "ops.csv").open(newline="") as handle:
        ops = {int(row["id"]): row for row in csv.DictReader(handle)}
    with (args.graph / "address_manifest.csv").open(newline="") as handle:
        addresses = {int(row["op_id"]): row for row in csv.DictReader(handle)}
    pages_by_partition = defaultdict(dict)
    tagged_ops = []
    for op_id, op in ops.items():
        match = EXPERT.match(op["task"])
        if not match:
            continue
        address = addresses[op_id]
        if address["tensor"] != "expert_weight" or int(address["bytes"]) != PAGE:
            raise AssertionError(op_id)
        partition = int(address["partition"])
        page = (int(match["layer"]), int(match["expert"]))
        base = int(address["address"])
        old = pages_by_partition[partition].setdefault(page, base)
        if old != base:
            raise AssertionError((partition, page, old, base))
        tagged_ops.append((op_id, partition, page, base))
    page_locations = {}
    for partition, pages in pages_by_partition.items():
        for index, page in enumerate(sorted(pages)):
            bank = 0 if args.policy == "all_bank0" else index % 16
            page_locations[partition, page] = (bank, index * ROWS_PER_PAGE)
    rows = []
    for op_id, partition, page, base in sorted(tagged_ops):
        bank, row_base = page_locations[partition, page]
        rows.append((op_id, bank, row_base, base, PAGE))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("op_id", "bank", "row_base", "address_base", "page_bytes"))
        writer.writerows(rows)
    print(json.dumps({"status": "FUNCTIONAL_ONLY", "policy": args.policy,
                      "tagged_ops": len(rows), "unique_pages": len(page_locations),
                      "rows_per_page": ROWS_PER_PAGE,
                      "capacity_evaluated": False}, indent=2))


if __name__ == "__main__":
    main()

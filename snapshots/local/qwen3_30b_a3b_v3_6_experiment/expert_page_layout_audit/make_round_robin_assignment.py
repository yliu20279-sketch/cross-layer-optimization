#!/usr/bin/env python3
"""Generate a deterministic full-model per-partition expert-page Bank control."""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--placement", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    placement = json.loads(args.placement.read_text())
    pages = defaultdict(list)
    for layer in range(48):
        for expert in range(128):
            rank = int(placement[str(layer)]["expert_to_rank"][str(expert)])
            pages[rank].append((layer, expert))
    rows = []
    for rank in range(16):
        for index, (layer, expert) in enumerate(sorted(pages[rank])):
            rows.append((layer, expert, rank, index % 16))
    assert len(rows) == 48 * 128
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("layer", "expert", "partition", "bank"))
        writer.writerows(rows)
    print(json.dumps({"status": "PASS", "pages": len(rows), "partitions": len(pages),
                      "policy": "round-robin within fixed expert owner"}, indent=2))


if __name__ == "__main__":
    main()

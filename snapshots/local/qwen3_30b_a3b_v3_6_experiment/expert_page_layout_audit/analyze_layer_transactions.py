#!/usr/bin/env python3
"""Stream a detailed Bank log and attribute wait to graph tensor classes."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def read_ops(graph: Path) -> dict[int, dict]:
    with (graph / "address_manifest.csv").open(newline="") as handle:
        return {int(row["op_id"]): row for row in csv.DictReader(handle)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    ops = read_ops(args.graph)
    by_tensor = defaultdict(Counter)
    by_tensor_bank = defaultdict(Counter)
    request_count = 0
    with (args.run / "bank_requests.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            request_count += 1
            op = ops[int(row["op_id"])]
            tensor = op["tensor"]
            bank = int(row["bankgroup"]) * 4 + int(row["bank"])
            wait = int(row["cross_request_bank_wait_ticks"])
            represented = float(row["represented_bytes"])
            by_tensor[tensor]["transactions"] += 1
            by_tensor[tensor]["wait_ticks"] += wait
            by_tensor[tensor]["waited_transactions"] += wait > 0
            by_tensor[tensor]["represented_bytes"] += represented
            by_tensor[tensor]["bank0_transactions"] += bank == 0
            by_tensor[tensor]["bank0_wait_ticks"] += wait if bank == 0 else 0
            by_tensor_bank[(tensor, bank)]["transactions"] += 1
            by_tensor_bank[(tensor, bank)]["wait_ticks"] += wait
    total_wait = sum(row["wait_ticks"] for row in by_tensor.values())
    total_tx = sum(row["transactions"] for row in by_tensor.values())
    total_bytes = sum(row["represented_bytes"] for row in by_tensor.values())
    result = {
        "status": "PASS",
        "transaction_count": request_count,
        "total_wait_ticks": total_wait,
        "total_represented_bytes": total_bytes,
        "by_tensor": {
            key: {**value, "wait_fraction": value["wait_ticks"] / total_wait if total_wait else 0}
            for key, value in sorted(by_tensor.items())
        },
        "by_tensor_bank": [
            {"tensor": tensor, "decoded_bank": bank, **value}
            for (tensor, bank), value in sorted(by_tensor_bank.items())
        ],
        "limitations": [
            "Wait is attributed to the waiting transaction's tensor class; blocker page identity is absent.",
            "One layer is a mechanism screen, not a 48-layer outcome.",
        ],
    }
    assert request_count == total_tx
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "transaction_count": request_count,
                      "total_wait_ticks": total_wait, "by_tensor": result["by_tensor"]}, indent=2))


if __name__ == "__main__":
    main()

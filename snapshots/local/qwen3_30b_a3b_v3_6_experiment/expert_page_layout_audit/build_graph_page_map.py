#!/usr/bin/env python3
"""Bind expert memory operations to Bank and row slots for a frozen graph."""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path


PAGE = 2_359_296
ROWS_PER_PAGE = 144
EXPERT_ROW_START = 4096  # Dedicated physical row range; untagged traffic stays below it.
ROW_ALIAS_LIMIT_BYTES = EXPERT_ROW_START * 256 * 64
WEIGHT = re.compile(r"^S\d+L(?P<layer>\d+)W\d+E(?P<expert>\d+)_weight_read$")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--placement", type=Path, required=True)
    parser.add_argument("--assignment", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    graph = json.loads((args.graph / "graph_manifest.json").read_text())
    if not graph.get("bank_aware_pager"):
        raise ValueError("graph must use the bank-aware pager")
    placement = json.loads(args.placement.read_text())
    with args.assignment.open(newline="") as handle:
        assignment_rows = list(csv.DictReader(handle))
    bank_of = {(int(r["layer"]), int(r["expert"])): int(r["bank"])
               for r in assignment_rows}
    assert len(bank_of) == 48 * 128
    with (args.graph / "ops.csv").open(newline="") as handle:
        ops = {int(r["id"]): r for r in csv.DictReader(handle)}
    with (args.graph / "address_manifest.csv").open(newline="") as handle:
        addresses = {int(r["op_id"]): r for r in csv.DictReader(handle)}
    expert_tensors = {"expert_weight", "expert_eviction", "expert_page_commit"}
    untagged = [r for r in addresses.values() if r["tensor"] not in expert_tensors]
    max_untagged_end = max(int(r["address"]) + int(r["bytes"]) for r in untagged)
    # Even ignoring Bank/Rank bits, ordinary addresses cannot reach row 4096.
    if max_untagged_end >= ROW_ALIAS_LIMIT_BYTES:
        raise ValueError("untagged traffic could overlap reserved expert rows")
    by_task = {r["task"]: op_id for op_id, r in ops.items()}
    pages_by_rank = defaultdict(list)
    for layer in range(48):
        for expert in range(128):
            rank = int(placement[str(layer)]["expert_to_rank"][str(expert)])
            pages_by_rank[rank].append((layer, expert))
    resident = {}
    next_slot = defaultdict(int)
    free_slots = defaultdict(list)
    capacity = graph["per_bank_page_capacity"]
    for rank, pages in pages_by_rank.items():
        for page in sorted(pages)[:graph["budget"]["cache_slots_per_partition"]]:
            bank = bank_of[page]
            slot = next_slot[rank, bank]
            assert slot < capacity
            next_slot[rank, bank] += 1
            resident[page] = (rank, bank, slot)
    commit_events = {int(e["commit"]): e for e in graph["page_operations"]}
    victim_reads = {}
    for event in graph["page_operations"]:
        commit_task = ops[int(event["commit"])]["task"]
        assert commit_task.endswith("_commit")
        victim_task = commit_task[:-len("_commit")] + "_victim_read"
        victim_reads[by_task[victim_task]] = tuple(event["victim"])
    output = []
    for op_id, op in ops.items():
        page = None
        event = commit_events.get(op_id)
        if event is not None:
            page = tuple(event["page"])
            victim = tuple(event["victim"])
            rank, victim_bank, slot = resident.pop(victim)
            bank = bank_of[page]
            if bank == victim_bank:
                new_slot = slot
            else:
                free_slots[rank, victim_bank].append(slot)
                if free_slots[rank, bank]:
                    new_slot = free_slots[rank, bank].pop()
                else:
                    new_slot = next_slot[rank, bank]
                    next_slot[rank, bank] += 1
                assert new_slot < capacity
            resident[page] = (rank, bank, new_slot)
        elif op_id in victim_reads:
            page = victim_reads[op_id]
        else:
            match = WEIGHT.match(op["task"])
            if match:
                page = (int(match["layer"]), int(match["expert"]))
        if page is None:
            continue
        address = addresses[op_id]
        assert address["tensor"] in ("expert_weight", "expert_eviction", "expert_page_commit")
        assert int(address["bytes"]) == PAGE
        rank, bank, row_slot = resident[page]
        assert rank == int(address["partition"])
        output.append((op_id, bank, EXPERT_ROW_START + row_slot * ROWS_PER_PAGE, int(address["address"]), PAGE))
    assert len(commit_events) == graph["misses"]
    assert len(output) == sum(r["tensor"] in expert_tensors for r in addresses.values())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("op_id", "bank", "row_base", "address_base", "page_bytes"))
        writer.writerows(output)
    print(json.dumps({"status": "PASS", "tagged_ops": len(output),
                      "page_misses": graph["misses"],
                      "max_untagged_address_end": max_untagged_end,
                      "expert_row_start": EXPERT_ROW_START,
                      "max_row_base": max(r[2] for r in output),
                      "per_bank_page_capacity": capacity}, indent=2))


if __name__ == "__main__":
    main()

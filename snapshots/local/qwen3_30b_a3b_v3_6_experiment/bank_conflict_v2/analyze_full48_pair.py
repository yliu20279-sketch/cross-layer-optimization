#!/usr/bin/env python3
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results/bank_fulltrace_c8_bursty_v1"
OUT = ROOT / "results/bank_fulltrace_c8_bursty_v1/full48_pair_analysis"


def read_events(kind):
    with (BASE / kind / "events.csv").open(newline="") as handle:
        return {int(r["id"]): r for r in csv.DictReader(handle)}


def f(row, key):
    return float(row[key])


def layer_of(task):
    m = re.search(r"L(\d+)", task)
    return int(m.group(1)) if m else -1


def aggregate_bank(kind):
    with (BASE / kind / "bank_aggregate.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    for r in rows:
        for k in r:
            if k not in ("partition", "bankgroup", "bank"):
                r[k] = float(r[k])
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    normal = read_events("normal_eventjump_v6")
    oracle = read_events("oracle_eventjump_v6")
    assert normal.keys() == oracle.keys()
    layer = defaultdict(lambda: {"ops": 0, "positive_done_delta_ops": 0,
                                 "sum_positive_done_delta": 0.0,
                                 "max_done_delta": 0.0,
                                 "normal_layer_completion": 0.0,
                                 "oracle_layer_completion": 0.0})
    owner = defaultdict(lambda: {"ops": 0, "normal_completion": 0.0,
                                 "oracle_completion": 0.0,
                                 "max_op_done_delta": 0.0})
    positive = []
    for op_id in sorted(normal):
        n, o = normal[op_id], oracle[op_id]
        assert n["task"] == o["task"] and n["kind"] == o["kind"]
        delta = f(n, "done") - f(o, "done")
        l = layer_of(n["task"])
        x = layer[l]
        x["ops"] += 1
        x["normal_layer_completion"] = max(x["normal_layer_completion"], f(n, "done"))
        x["oracle_layer_completion"] = max(x["oracle_layer_completion"], f(o, "done"))
        if delta > 0:
            x["positive_done_delta_ops"] += 1
            x["sum_positive_done_delta"] += delta
            x["max_done_delta"] = max(x["max_done_delta"], delta)
            positive.append({"id": op_id, "layer": l, "owner": int(n["inference_request_id"]),
                             "task": n["task"], "kind": n["kind"], "done_delta": delta,
                             "normal_done": f(n, "done"), "oracle_done": f(o, "done")})
        own = int(n["inference_request_id"])
        y = owner[own]
        y["ops"] += 1
        y["normal_completion"] = max(y["normal_completion"], f(n, "done"))
        y["oracle_completion"] = max(y["oracle_completion"], f(o, "done"))
        y["max_op_done_delta"] = max(y["max_op_done_delta"], delta)

    layer_rows = []
    for l, x in sorted(layer.items()):
        x = {"layer": l, **x}
        x["layer_completion_delta"] = x["normal_layer_completion"] - x["oracle_layer_completion"]
        layer_rows.append(x)
    owner_rows = []
    for own, x in sorted(owner.items()):
        x = {"owner": own, **x}
        x["completion_delta"] = x["normal_completion"] - x["oracle_completion"]
        owner_rows.append(x)

    banks = aggregate_bank("normal_eventjump_v6")
    total_wait = sum(r["cross_request_bank_wait_ticks"] for r in banks)
    total_tx = sum(r["transactions"] for r in banks)
    for r in banks:
        r["wait_share"] = r["cross_request_bank_wait_ticks"] / total_wait if total_wait else 0
        r["waited_transaction_fraction"] = r["transactions_with_cross_request_wait"] / r["transactions"] if r["transactions"] else 0
    banks.sort(key=lambda r: r["cross_request_bank_wait_ticks"], reverse=True)

    def write_csv(name, rows):
        if not rows:
            return
        with (OUT / name).open("w", newline="") as handle:
            w = csv.DictWriter(handle, fieldnames=rows[0].keys())
            w.writeheader(); w.writerows(rows)

    write_csv("layer_completion_deltas.csv", layer_rows)
    write_csv("request_completion_deltas.csv", owner_rows)
    write_csv("positive_operation_deltas.csv", sorted(positive, key=lambda r: r["done_delta"], reverse=True))
    write_csv("bank_hotspots.csv", banks)

    nv = json.loads((BASE / "normal_eventjump_v6/validation.json").read_text())
    ov = json.loads((BASE / "oracle_eventjump_v6/validation.json").read_text())
    delta = nv["total_cycles"] - ov["total_cycles"]
    report = {
        "status": "PASS",
        "normal_cycles": nv["total_cycles"],
        "oracle_cycles": ov["total_cycles"],
        "exposed_cross_request_bank_cycles": delta,
        "exposed_fraction": delta / nv["total_cycles"],
        "transaction_count": int(total_tx),
        "cumulative_cross_request_bank_wait_ticks": int(total_wait),
        "layers_with_positive_completion_delta": sum(r["layer_completion_delta"] > 0 for r in layer_rows),
        "requests_with_positive_completion_delta": sum(r["completion_delta"] > 0 for r in owner_rows),
        "operations_with_positive_done_delta": len(positive),
        "top_layers": sorted(layer_rows, key=lambda r: r["layer_completion_delta"], reverse=True)[:10],
        "request_deltas": owner_rows,
        "top_banks": banks[:10],
        "interpretation_limit": "Bank statistics are aggregate-only; exact layer/request-to-bank joins require detailed transaction logging or a new stratified logging run."
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

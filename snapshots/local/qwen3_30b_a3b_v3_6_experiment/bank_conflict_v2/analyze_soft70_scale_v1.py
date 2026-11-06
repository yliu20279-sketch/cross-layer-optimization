#!/usr/bin/env python3
"""Build conserving c1/c2/c4 evidence for the selected soft70 stress."""
import csv, hashlib, json, math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results/bank_memory_stress_full48_co_scale_strict_v2"
SUITE = ROOT / "results/bank_soft70_scale_v1"
COMPONENTS = ("Compute", "NoC", "DRAM service and non-cross-request memory wait",
              "Paging DMA", "Sync/other", "Strict cross-request Bank exposed")

def rows(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run_path(c, mode):
    return SUITE / "runs" / f"c{c}_soft70_{mode}"

def fairness(normal, oracle):
    a = json.loads((normal / "launch.json").read_text())
    b = json.loads((oracle / "launch.json").read_text())
    for key in ("binary_sha256", "ramulator_library_sha256", "graph_hashes", "deepstack_timing_sha256"):
        if a.get(key) != b.get(key):
            raise RuntimeError(f"paired {key} differs")
    ac, bc = dict(a["controls"]), dict(b["controls"])
    if bc.pop("HB_IGNORE_CROSS_REQUEST_BANK_TIMING", None) != "1":
        raise RuntimeError("oracle intervention missing")
    for controls in (ac, bc):
        controls.pop("HB_OUT", None); controls.pop("POPNET_STATS_DIR", None)
    if ac != bc:
        raise RuntimeError("non-intervention controls differ")

def critical_attribution(graph, run):
    ops = {int(x["id"]): x for x in rows(graph / "ops.csv")}
    events = {int(x["id"]): x for x in rows(run / "events.csv")}
    parents = defaultdict(list)
    for edge in rows(graph / "deps.csv"):
        parents[int(edge["dst"])].append(int(edge["src"]))
    current = max(events, key=lambda k: (float(events[k]["done"]), k))
    chain = []
    while True:
        chain.append(current)
        if not parents[current]: break
        ready = float(events[current]["ready"])
        current = max(parents[current], key=lambda k: (float(events[k]["done"]), k))
        if not math.isclose(float(events[current]["done"]), ready, abs_tol=1e-6):
            raise RuntimeError("critical predecessor mismatch")
    comp = {x: 0.0 for x in COMPONENTS}
    for opid in reversed(chain):
        op, event = ops[opid], events[opid]
        ready, start, done = map(float, (event["ready"], event["start"], event["done"]))
        wait, duration = max(0, start-ready), max(0, done-start)
        kind = op["kind"]
        if kind == "COMPUTE": comp["Compute"] += duration; comp["Sync/other"] += wait
        elif kind == "NET": comp["NoC"] += wait + duration
        elif kind in ("LOAD", "STORE"): comp["DRAM service and non-cross-request memory wait"] += wait + duration
        elif kind in ("DMA_H2D", "DMA_D2H"): comp["Paging DMA"] += wait + duration
        else: comp["Sync/other"] += wait + duration
    total = float(json.loads((run / "validation.json").read_text())["total_cycles"])
    if not math.isclose(sum(comp.values()), total, abs_tol=1e-6):
        raise RuntimeError("oracle attribution does not conserve")
    return total, comp

def bank_stats(path):
    data = rows(path)
    total = sum(int(x["transactions"]) for x in data)
    waited = sum(int(x["transactions_with_cross_request_wait"]) for x in data)
    wait_ticks = sum(float(x["cross_request_bank_wait_ticks"]) for x in data)
    queue_ticks = sum(float(x["controller_queue_ticks"]) for x in data)
    partitions = {int(x["partition"]) for x in data if int(x["transactions"]) > 0}
    banks = {int(x["bankgroup"])*4 + int(x["bank"]) for x in data if int(x["transactions"]) > 0}
    by_bank = defaultdict(int)
    for x in data: by_bank[int(x["bankgroup"])*4 + int(x["bank"])] += int(x["transactions"])
    return {"transactions": total, "transactions_with_wait": waited,
            "waited_transaction_fraction": waited/total,
            "cross_request_bank_wait_ticks": wait_ticks, "controller_queue_ticks": queue_ticks,
            "cross_request_share_of_controller_queue": wait_ticks/queue_ticks if queue_ticks else 0,
            "active_partitions": len(partitions), "active_global_banks": len(banks),
            "minimum_global_bank_fraction": min(by_bank[i]/total for i in range(16)),
            "maximum_global_bank_fraction": max(by_bank[i]/total for i in range(16))}

def main():
    cases, evidence = [], []
    for c in (1, 2, 4):
        normal, oracle = run_path(c, "normal"), run_path(c, "oracle")
        fairness(normal, oracle)
        for path in (normal, oracle):
            if json.loads((path / "validation.json").read_text())["status"] != "PASS":
                raise RuntimeError(f"failed validation: {path}")
        normal_total = float(json.loads((normal / "validation.json").read_text())["total_cycles"])
        oracle_total, comp = critical_attribution(SOURCE / "graphs" / f"c{c}_co", oracle)
        exposed = normal_total - oracle_total
        if exposed < -1e-6: raise RuntimeError("oracle slower than normal")
        comp["Strict cross-request Bank exposed"] = max(0, exposed)
        if not math.isclose(sum(comp.values()), normal_total, abs_tol=1e-6):
            raise RuntimeError("normal attribution does not conserve")
        stat = bank_stats(normal / "bank_aggregate.csv")
        if stat["active_partitions"] != 16 or stat["active_global_banks"] != 16:
            raise RuntimeError(f"coverage failed at c{c}")
        cases.append({"concurrency": c, "normal_cycles": normal_total,
                      "oracle_cycles": oracle_total, "strict_bank_exposed_cycles": max(0, exposed),
                      "strict_bank_exposed_fraction": max(0, exposed)/normal_total,
                      **comp, **stat, "conservation_error_cycles": sum(comp.values())-normal_total})
        for path in (normal / "validation.json", normal / "launch.json", normal / "events.csv",
                     normal / "bank_aggregate.csv", normal / "layer_bank_wait.csv",
                     oracle / "validation.json", oracle / "launch.json", oracle / "events.csv",
                     oracle / "bank_aggregate.csv"):
            evidence.append({"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": sha(path)})
    with (SUITE / "scale_components.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(cases[0])); writer.writeheader(); writer.writerows(cases)
    report = {"status": "PASS", "classification": "controlled soft70 Bank-hotspot address-mapping stress; not a natural Qwen3 workload",
              "definition": "Only paired normal-minus-oracle is strict cross-request same-Bank critical-path exposure.",
              "target_30_percent_reached_at_c4": cases[-1]["strict_bank_exposed_fraction"] >= 0.30,
              "cases": cases, "limitations": ["single deterministic captured cohort (n=1)", "no confidence interval", "address-mapping stress"]}
    (SUITE / "scale_report.json").write_text(json.dumps(report, indent=2) + "\n")
    (SUITE / "provenance.json").write_text(json.dumps({"status": "EVIDENCE_COMPLETE", "files": evidence}, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "cases": len(cases)}, indent=2))

if __name__ == "__main__": main()

#!/usr/bin/env python3
"""Conserving attribution and Bank distributions for selected alias stress."""
import csv, hashlib, json, math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results/bank_memory_stress_full48_co_scale_strict_v2"
SCREEN = ROOT / "results/bank_alias_pressure_screen_c4_v2"
SUITE = ROOT / "results/bank_alias_pressure_selected_scale_v1"
COMPONENTS = ("Compute", "NoC", "DRAM service and non-cross-request memory wait",
              "Paging DMA", "Sync/other", "Strict cross-request Bank exposed")

def read_rows(path):
    with path.open(newline="") as h: return list(csv.DictReader(h))

def sha256(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def paths(c, case, mode):
    if c == 4: return SCREEN / "runs" / f"{case}_{mode}"
    return SUITE / "runs" / f"c{c}_{case}_{mode}"

def fairness(normal, oracle):
    a, b = json.loads((normal / "launch.json").read_text()), json.loads((oracle / "launch.json").read_text())
    for key in ("binary_sha256", "ramulator_library_sha256", "graph_hashes", "deepstack_timing_sha256"):
        if a.get(key) != b.get(key): raise RuntimeError(f"paired {key} differs")
    ac, bc = dict(a["controls"]), dict(b["controls"])
    if bc.pop("HB_IGNORE_CROSS_REQUEST_BANK_TIMING", None) != "1": raise RuntimeError("oracle flag missing")
    for x in (ac, bc): x.pop("HB_OUT", None); x.pop("POPNET_STATS_DIR", None)
    if ac != bc: raise RuntimeError("non-intervention controls differ")

def critical(graph, run):
    ops = {int(x["id"]): x for x in read_rows(graph / "ops.csv")}
    ev = {int(x["id"]): x for x in read_rows(run / "events.csv")}
    parents = defaultdict(list)
    for x in read_rows(graph / "deps.csv"): parents[int(x["dst"])].append(int(x["src"]))
    cur = max(ev, key=lambda k: (float(ev[k]["done"]), k)); chain=[]
    while True:
        chain.append(cur)
        if not parents[cur]: break
        ready=float(ev[cur]["ready"]); cur=max(parents[cur], key=lambda k:(float(ev[k]["done"]),k))
        if not math.isclose(float(ev[cur]["done"]), ready, abs_tol=1e-6): raise RuntimeError("critical predecessor mismatch")
    comp={x:0.0 for x in COMPONENTS}
    for opid in reversed(chain):
        op,e=ops[opid],ev[opid]; ready,start,done=map(float,(e["ready"],e["start"],e["done"]))
        wait=max(0,start-ready); dur=max(0,done-start); kind=op["kind"]
        if kind=="COMPUTE": comp["Compute"]+=dur; comp["Sync/other"]+=wait
        elif kind=="NET": comp["NoC"]+=wait+dur
        elif kind in ("LOAD","STORE"): comp["DRAM service and non-cross-request memory wait"]+=wait+dur
        elif kind in ("DMA_H2D","DMA_D2H"): comp["Paging DMA"]+=wait+dur
        else: comp["Sync/other"]+=wait+dur
    total=float(json.loads((run/"validation.json").read_text())["total_cycles"])
    if not math.isclose(sum(comp.values()),total,abs_tol=1e-6): raise RuntimeError("oracle attribution does not conserve")
    return total,comp

def bank_stats(path):
    rows=read_rows(path); tx=sum(int(x["transactions"]) for x in rows); wt=sum(int(x["transactions_with_cross_request_wait"]) for x in rows)
    wait=sum(float(x["cross_request_bank_wait_ticks"]) for x in rows); queue=sum(float(x["controller_queue_ticks"]) for x in rows)
    return {"transactions":tx,"transactions_with_wait":wt,"waited_transaction_fraction":wt/tx,
            "cross_request_bank_wait_ticks":wait,"controller_queue_ticks":queue,
            "cross_request_share_of_controller_queue":wait/queue if queue else 0}

def main():
    screen=json.loads((SCREEN/"screen_report.json").read_text()); winner=screen["winner"]["case"]
    cases=[]; evidence=[]
    for c in (1,2,4):
      graph=SOURCE/"graphs"/f"c{c}_co"
      for case in ("balanced16",winner):
        n,o=paths(c,case,"normal"),paths(c,case,"oracle"); fairness(n,o)
        for p in (n,o):
          v=json.loads((p/"validation.json").read_text())
          if v["status"]!="PASS": raise RuntimeError(f"{p}: validation failed")
        nt=float(json.loads((n/"validation.json").read_text())["total_cycles"]); ot,comp=critical(graph,o)
        exposed=nt-ot
        if exposed < -1e-6: raise RuntimeError("oracle slower than normal")
        comp["Strict cross-request Bank exposed"]=max(0,exposed)
        if not math.isclose(sum(comp.values()),nt,abs_tol=1e-6): raise RuntimeError("normal attribution does not conserve")
        stats=bank_stats(n/"bank_aggregate.csv")
        cases.append({"concurrency":c,"mapping":"balanced" if case=="balanced16" else "alias",
          "case":case,"effective_banks":16 if case=="balanced16" else int(screen["winner"]["effective_banks"]),
          "normal_cycles":nt,"oracle_cycles":ot,"strict_bank_exposed_cycles":max(0,exposed),
          "strict_bank_exposed_fraction":max(0,exposed)/nt,**comp,**stats,
          "conservation_error_cycles":sum(comp.values())-nt})
        for p in (n/"validation.json",n/"launch.json",n/"events.csv",n/"bank_aggregate.csv",
                  o/"validation.json",o/"launch.json",o/"events.csv",o/"bank_aggregate.csv"):
          evidence.append({"path":str(p.relative_to(ROOT)),"bytes":p.stat().st_size,"sha256":sha256(p)})
    fields=list(cases[0]);
    with (SUITE/"scale_components.csv").open("w",newline="") as h:
      w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(cases)
    report={"status":"PASS","classification":"controlled address-mapping stress; not a natural Qwen3 workload",
      "selection_rule":screen["selection_rule"],"selected_case":winner,"selected_effective_banks":screen["winner"]["effective_banks"],
      "target_30_percent_reached_at_c4":next(x for x in cases if x["concurrency"]==4 and x["mapping"]=="alias")["strict_bank_exposed_fraction"]>=0.30,
      "definition":"Only paired normal-minus-oracle is strict cross-request same-Bank critical-path exposure.",
      "cases":cases,"limitations":["single deterministic captured cohort (n=1)","controlled address mapping stress", "no confidence interval"]}
    (SUITE/"scale_report.json").write_text(json.dumps(report,indent=2)+"\n")
    (SUITE/"provenance.json").write_text(json.dumps({"status":"EVIDENCE_COMPLETE","files":evidence},indent=2)+"\n")
    print(json.dumps({"status":"PASS","selected":winner,"cases":len(cases)},indent=2))

if __name__=="__main__": main()

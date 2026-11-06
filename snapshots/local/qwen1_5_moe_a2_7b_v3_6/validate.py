#!/usr/bin/env python3
import argparse, json
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",type=Path,required=True); a=ap.parse_args(); checks={}
    m=json.loads((a.root/"v3_6_mapping.json").read_text()); checks["pp4_tp4_ep4"]=m["parallelism"]=={"pipeline":4,"tensor":4,"expert":4}; checks["all_clusters_once"]={n for s in m["stages"].values() for n in s["clusters"]}=={f"N{i}" for i in range(16)}; checks["equal_expert_capacity"]=all(s["experts_per_rank_per_layer"]==15 for s in m["stages"].values())
    for phase in ("prefill","first_decode","incremental_decode"):
        g=json.loads((a.root/f"{phase}_graph.json").read_text()); ns=g["nodes"]; es=g["edges"]; ids=[n["node_id"] for n in ns]; idx={x:i for i,x in enumerate(ids)}
        checks[f"{phase}_dag"]=len(ids)==len(set(ids)) and all(e["src"] in idx and e["dst"] in idx and idx[e["src"]]<idx[e["dst"]] for e in es)
        checks[f"{phase}_24_layers"]={n["layer"] for n in ns if n["layer"]>=0}==set(range(24))
        checks[f"{phase}_24_router"]=sum(n["op"]=="router_top4" for n in ns)==24
        checks[f"{phase}_sem_collectives"]=sum(n["op"]=="sem_moe_shuffled_reduce_scatter" for n in ns)==24 and sum(n["op"]=="sem_moe_deferred_shuffled_allgather" for n in ns)==24
        checks[f"{phase}_top4_traffic"]=all(e["expert_activations"]==g["metadata"]["tokens"]*4 for e in es if e["traffic_class"] in ("expert_dispatch","expert_combine","expert_local"))
    cap=json.loads((a.root/"memory_feasibility.json").read_text()); checks["ideal_average_capacity_fit"]=cap["average_capacity_fits"]
    metrics=json.loads((a.root/"sem_moe_metrics.json").read_text()); checks["synthetic_not_mislabeled"]=metrics["trace_class"]=="synthetic_smoke_only"; checks["remote_not_worse_in_smoke"]=metrics["sem_moe"]["remote_activations"]<=metrics["baseline"]["remote_activations"]
    for mode in ("ep_baseline","hiband_only","hiband_sem_moe"):
        d=a.root/"legosim"/mode; ops=list(__import__('csv').DictReader((d/"ops.csv").open())); deps=list(__import__('csv').DictReader((d/"deps.csv").open()))
        checks[f"{mode}_legosim_schema"]=bool(ops) and all(len(r)==13 for r in ops) and bool(deps)
        checks[f"{mode}_addresses_in_v3_6"]=all(int(r["address"])<8*1024**3 for r in ops if r["kind"] in ("LOAD","STORE"))
    checks["sem_moe_less_legosim_net_bytes"]=sum(int(r["bytes"]) for r in __import__('csv').DictReader((a.root/"legosim/hiband_sem_moe/ops.csv").open()) if r["kind"]=="NET") <= sum(int(r["bytes"]) for r in __import__('csv').DictReader((a.root/"legosim/hiband_only/ops.csv").open()) if r["kind"]=="NET")
    out={"status":"PASS" if all(checks.values()) else "FAIL","checks":checks}; (a.root/"validation.json").write_text(json.dumps(out,indent=2)+"\n"); print(json.dumps(out,indent=2)); raise SystemExit(0 if out["status"]=="PASS" else 1)
if __name__=="__main__": main()

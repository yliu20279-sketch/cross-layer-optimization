#!/usr/bin/env python3
import argparse,json,hashlib
from pathlib import Path
def main():
 a=argparse.ArgumentParser();a.add_argument("--root",required=True);x=a.parse_args();r=Path(x.root);m=json.loads((r/"manifest.json").read_text());c={"three_phases":set(m["graphs"])=={"prefill","first_decode","incremental_decode"},"analytical_boundary":m["evidence"]=="analytical_not_profiled"}
 for ph in m["graphs"]:
  g=json.loads((r/f"{ph}_graph.json").read_text());ns=g["nodes"];es=g["edges"];ids=[n["node_id"] for n in ns];pos={v:i for i,v in enumerate(ids)};c[f"{ph}_dag"]=len(ids)==len(set(ids)) and all(e["src"] in pos and e["dst"] in pos and pos[e["src"]]<pos[e["dst"]] for e in es);c[f"{ph}_24_moe_layers"]={n["layer"] for n in ns if 0<=n["layer"]<24}==set(range(24)) and sum(n["op"]=="router_logits_softmax_top4" for n in ns)==24;c[f"{ph}_score_tiled"]=all(e["logical_bytes_global"]>0 and e["materialized_bytes_global"]==0 for e in es if e["dependency_kind"]=="fused_tile");c[f"{ph}_no_gpu"]=all("GPU" not in n["execution_unit"] for n in ns)
 cap=json.loads((r/"memory_feasibility.json").read_text());c["8GiB_target"]=cap["capacity_bytes_total"]==8*2**30 and cap["capacity_bytes_per_partition"]==512*2**20;c["conditional_static_fit"]=cap["status"]=="STATIC_IDEAL_W4_FITS_CONDITIONALLY" and cap["per_partition"]["headroom_bytes"]>0;c["balanced_90_entries"]=set(cap["expert_entries_per_partition"].values())=={90}
 rows=(r/"layer_expert_placement.csv").read_text(encoding="utf-8-sig").splitlines();c["1440_unique_placements"]=len(rows)==1441
 mp=json.loads((r/"v3_6_mapping_manifest.json").read_text());c["not_execution_claimed"]=mp["execution"]=="NOT_RUN";snap=json.loads((r/"v3_6_source_snapshot.json").read_text());arch=r.parents[1]/"whisper_operator_inventory"/"target_architecture_v3_6";c["v3_6_sources_unchanged"]=all(hashlib.sha256((arch/z["file"]).read_bytes()).hexdigest()==z["sha256"] for z in snap["files"])
 o={"status":"PASS" if all(c.values()) else "FAIL","checks":c};(r/"validation.json").write_text(json.dumps(o,indent=2)+"\n");print(json.dumps(o,indent=2));raise SystemExit(0 if o["status"]=="PASS" else 1)
if __name__=="__main__":main()

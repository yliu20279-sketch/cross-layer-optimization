#!/usr/bin/env python3
import argparse, csv, hashlib, json
from pathlib import Path

SCHEMES = ("baseline_ep", "hiband", "sem_moe", "hiband_sem_moe")

def rows(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    graphs = {s: a.root / s for s in SCHEMES}
    manifests = {s: json.loads((p / "graph_manifest.json").read_text()) for s,p in graphs.items()}
    ops = {s: rows(p / "ops.csv") for s,p in graphs.items()}
    report = {"schema":"strict-four-graph-audit-v1", "cases":{}, "checks":[]}
    failures=[]

    frozen=("context","batch","steps","microbatch_size","cohort_policy","cohort_repeat",
            "partition_capacity_mib","capacity_class","compute_timing","request_ids",
            "inference_request_id_map")
    ref=manifests["baseline_ep"]
    for key in frozen:
        if any(manifests[s][key] != ref[key] for s in SCHEMES):
            failures.append(f"frozen manifest field differs: {key}")
    report["checks"].append("frozen manifest fields identical")

    for s in SCHEMES:
        mem=[r for r in ops[s] if r["kind"] in ("LOAD","STORE")]
        bad=[r["id"] for r in mem if int(r["inference_request_id"]) < 0]
        expert=[r for r in ops[s] if r["kind"]=="COMPUTE" and "_SwiGLU" in r["task"]]
        report["cases"][s]={
            "operations":len(ops[s]), "dependencies_sha256":digest(graphs[s]/"deps.csv"),
            "memory_operations":len(mem), "ownerless_memory_operations":len(bad),
            "expert_compute_operations":len(expert),
            "expert_compute_cycles":sum(int(r["cycles"]) for r in expert),
            "total_compute_cycles":sum(int(r["cycles"]) for r in ops[s] if r["kind"]=="COMPUTE"),
            "net_bytes":sum(int(r["bytes"]) for r in ops[s] if r["kind"]=="NET"),
            "page_misses":manifests[s]["misses"]
        }
        if bad: failures.append(f"{s}: {len(bad)} ownerless memory operations")

    def paired_only_hiband(a_name,b_name):
        aa,bb=ops[a_name],ops[b_name]
        if len(aa)!=len(bb): return False,"operation count"
        allowed={"phase","scope"}
        for x,y in zip(aa,bb):
            if any(x[k]!=y[k] for k in x if k not in allowed):
                return False,f"op {x['id']} non-HiBand field"
        if (graphs[a_name]/"deps.csv").read_bytes() != (graphs[b_name]/"deps.csv").read_bytes():
            return False,"dependency graph"
        return True,""
    for x,y in (("baseline_ep","hiband"),("sem_moe","hiband_sem_moe")):
        ok,why=paired_only_hiband(x,y)
        if not ok: failures.append(f"{x}/{y} differs in {why}")
    report["checks"].append("HiBand paired graphs differ only in phase/scope")

    expert_counts={report["cases"][s]["expert_compute_operations"] for s in SCHEMES}
    expert_cycles={report["cases"][s]["expert_compute_cycles"] for s in SCHEMES}
    total_compute={report["cases"][s]["total_compute_cycles"] for s in SCHEMES}
    if len(expert_counts)!=1: failures.append("expert compute operation count differs")
    if len(expert_cycles)!=1: failures.append("expert compute cycles differ")
    if len(total_compute)!=1: failures.append("total compute cycles differ")
    report["checks"].append("compute work conserved across placement schemes")
    report["status"]="FAIL" if failures else "PASS"
    report["failures"]=failures
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,indent=2,sort_keys=True))
    raise SystemExit(1 if failures else 0)

if __name__=="__main__": main()

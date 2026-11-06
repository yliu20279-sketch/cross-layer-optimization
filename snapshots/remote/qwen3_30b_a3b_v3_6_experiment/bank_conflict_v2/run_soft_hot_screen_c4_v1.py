#!/usr/bin/env python3
"""Full-transaction c4 soft Bank-hotspot screen with strict paired oracle."""
import concurrent.futures, hashlib, json, os, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; HERE=Path(__file__).resolve().parent
SOURCE=ROOT/"results/bank_memory_stress_full48_co_scale_strict_v2"
SUITE=ROOT/"results/bank_soft_hot_screen_c4_v1"
GRAPH=SOURCE/"graphs/c4_co"; RELEASES=SOURCE/"releases/simultaneous_c4.csv"
BINARY=ROOT/"toolchain/popnet_cross_request_release_v2/build_layer_heatmap_v1/popnet"
RAM=ROOT/"toolchain/ramulator2_cross_request_v1/libramulator_soft_hot_v1.so"
CASES=(50,70,85)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def run(job):
    pct,mode=job; out=SUITE/"runs"/f"soft{pct}_{mode}"
    cmd=[sys.executable,HERE/"run_arrival_sampling.py","--root",ROOT,"--graph",GRAPH,"--out",out,"--binary",BINARY,"--ramulator-library",RAM,"--request-releases",RELEASES,"--hiband","--max-outstanding-per-op","1","--bank-address-mode","soft_hot","--effective-banks","16","--soft-hot-percent",str(pct),"--bank-field-shift","14","--timeout-seconds","43200"]
    if mode=="oracle": cmd.append("--ignore-cross-request-bank-timing")
    env=os.environ.copy(); env["PYTHONPATH"]=str(ROOT)+os.pathsep+env.get("PYTHONPATH",""); env["HB_BANK_LOG_DETAIL"]="0"
    logs=SUITE/"launcher_logs"; logs.mkdir(parents=True,exist_ok=True)
    with (logs/f"soft{pct}_{mode}.log").open("w") as h: rc=subprocess.run([str(x) for x in cmd],cwd=ROOT,env=env,stdout=h,stderr=subprocess.STDOUT).returncode
    return {"case":f"soft{pct}","mode":mode,"returncode":rc,"status":"PASS" if rc==0 else "FAIL"}
def main():
    SUITE.mkdir(parents=True,exist_ok=True)
    design={"status":"FROZEN","classification":"controlled soft Bank-hotspot address-mapping stress; not a natural Qwen3 workload","model":"Qwen3-30B-A3B","layers":48,"context":512,"concurrency":4,"compute_multiplier":0.25,"max_outstanding_per_memory_op":1,"arrival":"simultaneous","cases":["soft-hot-50","soft-hot-70","soft-hot-85"],"global_bank_coverage_requirement":"all decoded Bank IDs 0-15 must have nonzero transactions; each cold Bank target >=0.5%","partition_coverage_requirement":"all 16 partitions must have nonzero transactions","paired_oracle":"only cross-request same-Bank timing blockers removed; global row state preserved","fixed_hot_banks":[0,4,12,14],"mapping_note":"owner-independent deterministic mapping from accepted original address; only decoded Bank changes; physical address, Row, Column, partition, DAG, transactions, bytes, Compute and NoC remain unchanged","binary_sha256":sha(BINARY),"ramulator_sha256":sha(RAM),"limitations":["single deterministic captured cohort (n=1)","address-mapping stress"]}
    (SUITE/"frozen_design.json").write_text(json.dumps(design,indent=2)+"\n")
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool: status=list(pool.map(run,[(p,m) for p in CASES for m in ("normal","oracle")]))
    (SUITE/"launcher_status.json").write_text(json.dumps(status,indent=2)+"\n")
    if any(x["returncode"] for x in status): raise SystemExit(1)
    print(json.dumps({"status":"PASS","runs":len(status)},indent=2))
if __name__=="__main__": main()

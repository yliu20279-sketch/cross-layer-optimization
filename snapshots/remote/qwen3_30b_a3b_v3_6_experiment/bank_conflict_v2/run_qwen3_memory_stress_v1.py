#!/usr/bin/env python3
import concurrent.futures, json, os, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];HERE=Path(__file__).resolve().parent
SUITE=ROOT/"results/bank_memory_stress_v1"
CASES=("ctx512_c16_high_L47_l4_c025","ctx512_c16_low_L25_l4_c025")
BINARY=ROOT/"toolchain/popnet_cross_request_release_v2/build_outstanding_v7/popnet"
RAM=ROOT/"toolchain/ramulator2_cross_request_v1/libramulator.so"
RELEASE=ROOT/"results/bank_pressure_screen_v1/releases/simultaneous_c16.csv"

def one(item):
    case,mode=item;out=SUITE/"runs"/f"{case}_{mode}"
    cmd=[sys.executable,HERE/"run_arrival_sampling.py","--root",ROOT,"--graph",SUITE/"graphs"/case,"--out",out,"--binary",BINARY,"--ramulator-library",RAM,"--request-releases",RELEASE,"--hiband","--max-outstanding-per-op",1,"--timeout-seconds",3600]
    if mode=="oracle":cmd.append("--ignore-cross-request-bank-timing")
    env=os.environ.copy();env["HB_BANK_LOG_DETAIL"]="0";logs=SUITE/"launcher_logs";logs.mkdir(parents=True,exist_ok=True)
    with (logs/f"{case}_{mode}.log").open("w") as h:r=subprocess.run(list(map(str,cmd)),cwd=ROOT,env=env,stdout=h,stderr=subprocess.STDOUT)
    return {"case":case,"mode":mode,"returncode":r.returncode,"status":"PASS" if r.returncode==0 else "FAIL"}

def main():
    jobs=[(c,m) for c in CASES for m in ("normal","oracle")]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as p:status=list(p.map(one,jobs))
    (SUITE/"launcher_status.json").write_text(json.dumps(status,indent=2)+"\n")
    if any(x["returncode"] for x in status):print(json.dumps(status,indent=2));raise SystemExit(1)
    rows=[]
    for c in CASES:
        n=json.loads((SUITE/"runs"/f"{c}_normal/validation.json").read_text());o=json.loads((SUITE/"runs"/f"{c}_oracle/validation.json").read_text());d=n["total_cycles"]-o["total_cycles"]
        rows.append({"case":c,"normal_cycles":n["total_cycles"],"oracle_cycles":o["total_cycles"],"exposed_bank_cycles":d,"exposed_fraction":d/n["total_cycles"]})
    report={"status":"PASS","classification":"synthetic memory-stress on captured Qwen3 routes","full_memory_trace":True,"lanes":4,"compute_multiplier":0.25,"max_outstanding_per_op":1,"pairs":rows}
    (SUITE/"pair_report.json").write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report,indent=2))
if __name__=="__main__":main()

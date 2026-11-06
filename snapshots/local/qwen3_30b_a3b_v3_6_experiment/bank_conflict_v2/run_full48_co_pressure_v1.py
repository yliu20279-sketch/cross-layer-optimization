#!/usr/bin/env python3
import concurrent.futures,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];HERE=Path(__file__).resolve().parent;SUITE=ROOT/"results/bank_memory_stress_full48_co_v1"
def one(mode):
 out=SUITE/mode;cmd=[sys.executable,HERE/"run_arrival_sampling.py","--root",ROOT,"--graph",SUITE/"stress_graph","--out",out,"--binary",ROOT/"toolchain/popnet_cross_request_release_v2/build_outstanding_v7/popnet","--ramulator-library",ROOT/"toolchain/ramulator2_cross_request_v1/libramulator.so","--request-releases",ROOT/"results/bank_pressure_screen_v1/releases/simultaneous_c16.csv","--hiband","--max-outstanding-per-op",1,"--timeout-seconds",14400]
 if mode=="oracle":cmd.append("--ignore-cross-request-bank-timing")
 env=os.environ.copy();env["HB_BANK_LOG_DETAIL"]="0"
 with (SUITE/f"{mode}_launcher.log").open("w") as h:r=subprocess.run(list(map(str,cmd)),cwd=ROOT,env=env,stdout=h,stderr=subprocess.STDOUT)
 return {"mode":mode,"returncode":r.returncode,"status":"PASS" if r.returncode==0 else "FAIL"}
def main():
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as p:s=list(p.map(one,("normal","oracle")))
 (SUITE/"launcher_status.json").write_text(json.dumps(s,indent=2)+"\n")
 if any(x["returncode"] for x in s):raise SystemExit(1)
 n=json.loads((SUITE/"normal/validation.json").read_text());o=json.loads((SUITE/"oracle/validation.json").read_text());d=n["total_cycles"]-o["total_cycles"]
 r={"status":"PASS","classification":"full-48-layer synthetic C+O memory stress on captured Qwen3 routes","context":512,"concurrency":16,"route_policy":"exploratory_low_skew","full_memory_trace":True,"compute_multiplier":0.25,"max_outstanding_per_op":1,"lanes4":False,"normal_cycles":n["total_cycles"],"oracle_cycles":o["total_cycles"],"exposed_bank_cycles":d,"exposed_fraction":d/n["total_cycles"]}
 (SUITE/"pair_report.json").write_text(json.dumps(r,indent=2)+"\n");print(json.dumps(r,indent=2))
if __name__=="__main__":main()

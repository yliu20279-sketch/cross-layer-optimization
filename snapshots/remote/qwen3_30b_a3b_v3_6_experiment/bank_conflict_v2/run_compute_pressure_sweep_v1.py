#!/usr/bin/env python3
import concurrent.futures,csv,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];HERE=Path(__file__).resolve().parent;SUITE=ROOT/"results/bank_compute_pressure_sweep_v1";BASE=ROOT/"results/bank_pressure_screen_v1"
CASES=("ctx512_c16_low_L25","ctx512_c16_high_L47");MULTS=(0.125,0.0625);BINARY=ROOT/"toolchain/popnet_cross_request_release_v2/build_outstanding_v7/popnet";RAM=ROOT/"toolchain/ramulator2_cross_request_v1/libramulator.so";RELEASE=BASE/"releases/simultaneous_c16.csv"
def label(x):return str(x).replace(".","p")
def prep(case,m):
 out=SUITE/"graphs"/f"{case}_c{label(m)}"
 if not (out/"memory_stress_manifest.json").exists():subprocess.run(list(map(str,[sys.executable,HERE/"build_qwen3_memory_stress.py","--input",BASE/"graphs"/case,"--output",out,"--lanes",0,"--compute-multiplier",m])),cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
 return out
def one(job):
 case,m,mode=job;name=f"{case}_c{label(m)}";out=SUITE/"runs"/f"{name}_{mode}";cmd=[sys.executable,HERE/"run_arrival_sampling.py","--root",ROOT,"--graph",prep(case,m),"--out",out,"--binary",BINARY,"--ramulator-library",RAM,"--request-releases",RELEASE,"--hiband","--max-outstanding-per-op",1,"--timeout-seconds",3600]
 if mode=="oracle":cmd.append("--ignore-cross-request-bank-timing")
 env=os.environ.copy();env["HB_BANK_LOG_DETAIL"]="0";logs=SUITE/"launcher_logs";logs.mkdir(parents=True,exist_ok=True)
 with (logs/f"{name}_{mode}.log").open("w") as h:r=subprocess.run(list(map(str,cmd)),cwd=ROOT,env=env,stdout=h,stderr=subprocess.STDOUT)
 return {"case":case,"compute_multiplier":m,"mode":mode,"status":"PASS" if r.returncode==0 else "FAIL","returncode":r.returncode}
def main():
 SUITE.mkdir(parents=True,exist_ok=True);(SUITE/"frozen_design.json").write_text(json.dumps({"cases":CASES,"compute_multipliers":MULTS,"max_outstanding_per_op":1,"lanes":0,"full_memory_trace":True,"target_waited_transaction_fraction":0.11511124042483495},indent=2)+"\n")
 for c in CASES:
  for m in MULTS:prep(c,m)
 jobs=[(c,m,z) for c in CASES for m in MULTS for z in ("normal","oracle")]
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as p:s=list(p.map(one,jobs))
 (SUITE/"launcher_status.json").write_text(json.dumps(s,indent=2)+"\n")
 if any(x["returncode"] for x in s):raise SystemExit(1)
 out=[]
 for c in CASES:
  for m in MULTS:
   name=f"{c}_c{label(m)}";np=SUITE/"runs"/f"{name}_normal";op=SUITE/"runs"/f"{name}_oracle";n=json.loads((np/"validation.json").read_text());o=json.loads((op/"validation.json").read_text());d=n["total_cycles"]-o["total_cycles"]
   with (np/"bank_aggregate.csv").open(newline="") as h:rs=list(csv.DictReader(h))
   tx=sum(int(x["transactions"]) for x in rs);wt=sum(int(x["transactions_with_cross_request_wait"]) for x in rs);ticks=sum(int(x["cross_request_bank_wait_ticks"]) for x in rs);queue=sum(int(x["controller_queue_ticks"]) for x in rs)
   out.append({"case":c,"compute_multiplier":m,"normal_cycles":n["total_cycles"],"oracle_cycles":o["total_cycles"],"exposed_cycles":d,"exposed_fraction":d/n["total_cycles"],"transactions":tx,"waited_transactions":wt,"waited_transaction_fraction":wt/tx,"cross_wait_ticks":ticks,"cross_queue_share":ticks/queue})
 r={"status":"PASS","classification":"real c16 routes with synthetic compute-intensity stress","baseline_full48_waited_fraction":0.11511124042483495,"cases":out,"exceeds_baseline":[x for x in out if x["waited_transaction_fraction"]>0.11511124042483495]};(SUITE/"sweep_report.json").write_text(json.dumps(r,indent=2)+"\n");print(json.dumps(r,indent=2))
if __name__=="__main__":main()

#!/usr/bin/env python3
import concurrent.futures,csv,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];HERE=Path(__file__).resolve().parent;SUITE=ROOT/"results/bank_replay_concurrency_screen_v1"
SOURCE=ROOT/"results/bank_memory_stress_ablation_v1/graphs"
BASES=("ctx512_c16_low_L25_nLCO","ctx512_c16_high_L47_nLCO");COPIES=(2,4)
BINARY=ROOT/"toolchain/popnet_cross_request_release_v2/build_outstanding_v7/popnet";RAM=ROOT/"toolchain/ramulator2_cross_request_v1/libramulator.so"
def graph_name(base,copies):return f"{base}_c{16*copies}_replay"
def prepare(base,copies):
 out=SUITE/"graphs"/graph_name(base,copies)
 if not (out/"replay_manifest.json").exists():subprocess.run(list(map(str,[sys.executable,HERE/"replicate_request_dag.py","--input",SOURCE/base,"--output",out,"--copies",copies])),cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
 return out
def release(batch):
 p=SUITE/"releases"/f"simultaneous_c{batch}.csv";p.parent.mkdir(parents=True,exist_ok=True)
 if not p.exists():
  with p.open("w",newline="") as h:
   w=csv.writer(h);w.writerow(("owner","release_cycle"));w.writerows((i,0) for i in range(batch))
 return p
def one(job):
 base,copies,mode=job;batch=16*copies;name=graph_name(base,copies);out=SUITE/"runs"/f"{name}_{mode}"
 cmd=[sys.executable,HERE/"run_arrival_sampling.py","--root",ROOT,"--graph",prepare(base,copies),"--out",out,"--binary",BINARY,"--ramulator-library",RAM,"--request-releases",release(batch),"--hiband","--max-outstanding-per-op",1,"--timeout-seconds",3600]
 if mode=="oracle":cmd.append("--ignore-cross-request-bank-timing")
 env=os.environ.copy();env["HB_BANK_LOG_DETAIL"]="0";logs=SUITE/"launcher_logs";logs.mkdir(parents=True,exist_ok=True)
 with (logs/f"{name}_{mode}.log").open("w") as h:r=subprocess.run(list(map(str,cmd)),cwd=ROOT,env=env,stdout=h,stderr=subprocess.STDOUT)
 return {"case":name,"mode":mode,"returncode":r.returncode,"status":"PASS" if r.returncode==0 else "FAIL"}
def main():
 SUITE.mkdir(parents=True,exist_ok=True);(SUITE/"frozen_design.json").write_text(json.dumps({"base_cases":BASES,"copies":COPIES,"effective_concurrency":[32,64],"classification":"synthetic replay-expanded concurrency","compute_multiplier":.25,"max_outstanding_per_op":1,"full_memory_trace":True,"promotion_threshold_waited_transaction_fraction":0.11511124042483495},indent=2)+"\n")
 for b in BASES:
  for c in COPIES:prepare(b,c);release(16*c)
 jobs=[(b,c,m) for b in BASES for c in COPIES for m in ("normal","oracle")]
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as p:s=list(p.map(one,jobs))
 (SUITE/"launcher_status.json").write_text(json.dumps(s,indent=2)+"\n")
 if any(x["returncode"] for x in s):raise SystemExit(1)
 rows=[]
 for b in BASES:
  for c in COPIES:
   name=graph_name(b,c);np=SUITE/"runs"/f"{name}_normal";op=SUITE/"runs"/f"{name}_oracle";n=json.loads((np/"validation.json").read_text());o=json.loads((op/"validation.json").read_text());d=n["total_cycles"]-o["total_cycles"]
   with (np/"bank_aggregate.csv").open(newline="") as h:rs=list(csv.DictReader(h))
   tx=sum(int(x["transactions"]) for x in rs);wt=sum(int(x["transactions_with_cross_request_wait"]) for x in rs);ticks=sum(int(x["cross_request_bank_wait_ticks"]) for x in rs);queue=sum(int(x["controller_queue_ticks"]) for x in rs)
   rows.append({"case":name,"effective_concurrency":16*c,"normal_cycles":n["total_cycles"],"oracle_cycles":o["total_cycles"],"exposed_cycles":d,"exposed_fraction":d/n["total_cycles"],"transactions":tx,"waited_transactions":wt,"waited_transaction_fraction":wt/tx,"cross_wait_ticks":ticks,"cross_queue_share":ticks/queue})
 report={"status":"PASS","classification":"synthetic replay-expanded concurrency","baseline_full48_waited_fraction":0.11511124042483495,"cases":rows,"exceeds_baseline":[x for x in rows if x["waited_transaction_fraction"]>0.11511124042483495]}
 (SUITE/"screen_report.json").write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report,indent=2))
if __name__=="__main__":main()

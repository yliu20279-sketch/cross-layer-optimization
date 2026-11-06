#!/usr/bin/env python3
import concurrent.futures,csv,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];HERE=Path(__file__).resolve().parent;SUITE=ROOT/"results/bank_memory_stress_full48_co_scale_strict_v2";SCALES=(1,2,4,8,16)
BINARY=ROOT/"toolchain/popnet_cross_request_release_v2/build_outstanding_v7/popnet";RAM=ROOT/"toolchain/ramulator2_cross_request_v1/libramulator.so"
def env():
 e=os.environ.copy();e["PYTHONPATH"]=str(ROOT)+os.pathsep+e.get("PYTHONPATH","");e["HB_BANK_LOG_DETAIL"]="0";return e
def release(c):
 p=SUITE/"releases"/f"simultaneous_c{c}.csv";p.parent.mkdir(parents=True,exist_ok=True)
 if not p.exists():
  with p.open("w",newline="") as h:w=csv.writer(h);w.writerow(("owner","release_cycle"));w.writerows((i,0) for i in range(c))
 return p
def prepare(c):
 base=SUITE/"graphs"/f"c{c}_base";stress=SUITE/"graphs"/f"c{c}_co"
 if not (base/"graph_manifest.json").exists():
  cmd=[sys.executable,HERE/"build_arrival_sampling_graph.py","--root",ROOT,"--context",512,"--batch",c,"--steps",1,"--layer-start",0,"--layers",48,"--microbatch-size",1,"--partition-capacity-mib",512,"--cohort-policy","exploratory_low_skew","--cohort-repeat",1,"--placement",ROOT/"results/sem_moe_reproduction_ctx512_v2/placement.json","--compute-profile",ROOT/"scalesim_compute_profile_v1.json","--hiband","--full-memory-trace","--out",base]
  subprocess.run(list(map(str,cmd)),cwd=ROOT,env=env(),check=True,stdout=subprocess.DEVNULL)
 if not (stress/"memory_stress_manifest.json").exists():subprocess.run(list(map(str,[sys.executable,HERE/"build_qwen3_memory_stress.py","--input",base,"--output",stress,"--lanes",0,"--compute-multiplier",.25])),cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
 return stress
def one(job):
 c,mode=job;out=SUITE/"runs"/f"c{c}_{mode}";cmd=[sys.executable,HERE/"run_arrival_sampling.py","--root",ROOT,"--graph",prepare(c),"--out",out,"--binary",BINARY,"--ramulator-library",RAM,"--request-releases",release(c),"--hiband","--max-outstanding-per-op",1,"--timeout-seconds",14400]
 if mode=="oracle":cmd.append("--ignore-cross-request-bank-timing")
 logs=SUITE/"launcher_logs";logs.mkdir(parents=True,exist_ok=True)
 with (logs/f"c{c}_{mode}.log").open("w") as h:r=subprocess.run(list(map(str,cmd)),cwd=ROOT,env=env(),stdout=h,stderr=subprocess.STDOUT)
 return {"scale":c,"mode":mode,"returncode":r.returncode,"status":"PASS" if r.returncode==0 else "FAIL"}
def main():
 SUITE.mkdir(parents=True,exist_ok=True);(SUITE/"frozen_design.json").write_text(json.dumps({"scales":[1,2,4,8,16],"run_here":SCALES,"oracle":"strict cross-request same-Bank timing only; global row state preserved","context":512,"route_policy":"exploratory_low_skew","layers":48,"full_memory_trace":True,"compute_multiplier":.25,"max_outstanding_per_op":1,"lanes":0,"arrival":"simultaneous","max_workers":2},indent=2)+"\n")
 for c in SCALES:prepare(c);release(c)
 jobs=[(c,m) for c in SCALES for m in ("normal","oracle")]
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as p:s=list(p.map(one,jobs))
 (SUITE/"launcher_status.json").write_text(json.dumps(s,indent=2)+"\n")
 if any(x["returncode"] for x in s):raise SystemExit(1)
 print(json.dumps({"status":"PASS","runs":len(s)},indent=2))
if __name__=="__main__":main()

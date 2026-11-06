#!/usr/bin/env python3
import concurrent.futures,csv,json,os,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];HERE=Path(__file__).resolve().parent
SUITE=ROOT/"results/bank_memory_stress_ablation_v1"
BASE=ROOT/"results/bank_pressure_screen_v1"
STRESS=ROOT/"results/bank_memory_stress_v1"
BINARY=ROOT/"toolchain/popnet_cross_request_release_v2/build_outstanding_v7/popnet"
RAM=ROOT/"toolchain/ramulator2_cross_request_v1/libramulator.so"
RELEASE=BASE/"releases/simultaneous_c16.csv"
CASES=("ctx512_c16_low_L25","ctx512_c16_high_L47")
CONFIGS=((1,0,0),(0,1,0),(0,0,1),(1,1,0),(1,0,1),(0,1,1))

def tag(cfg):
    l,c,o=cfg;return "".join(("L" if l else "nL","C" if c else "nC","O" if o else "nO"))

def prepare(case,cfg):
    l,c,o=cfg;dst=SUITE/"graphs"/f"{case}_{tag(cfg)}"
    if (dst/"memory_stress_manifest.json").exists():return dst
    cmd=[sys.executable,HERE/"build_qwen3_memory_stress.py","--input",BASE/"graphs"/case,"--output",dst,"--lanes",4 if l else 0,"--compute-multiplier",.25 if c else 1.0]
    subprocess.run(list(map(str,cmd)),cwd=ROOT,check=True,stdout=subprocess.DEVNULL);return dst

def one(job):
    case,cfg,mode=job;l,c,o=cfg;graph=prepare(case,cfg);name=f"{case}_{tag(cfg)}";out=SUITE/"runs"/f"{name}_{mode}"
    cmd=[sys.executable,HERE/"run_arrival_sampling.py","--root",ROOT,"--graph",graph,"--out",out,"--binary",BINARY,"--ramulator-library",RAM,"--request-releases",RELEASE,"--hiband","--timeout-seconds",3600]
    if o:cmd += ["--max-outstanding-per-op",1]
    if mode=="oracle":cmd.append("--ignore-cross-request-bank-timing")
    env=os.environ.copy();env["HB_BANK_LOG_DETAIL"]="0";logs=SUITE/"launcher_logs";logs.mkdir(parents=True,exist_ok=True)
    with (logs/f"{name}_{mode}.log").open("w") as h:r=subprocess.run(list(map(str,cmd)),cwd=ROOT,env=env,stdout=h,stderr=subprocess.STDOUT)
    return {"case":case,"config":tag(cfg),"mode":mode,"returncode":r.returncode,"status":"PASS" if r.returncode==0 else "FAIL"}

def pair_row(case,label,npath,opath,l,c,o,source):
    n=json.loads(npath.read_text());q=json.loads(opath.read_text());d=n["total_cycles"]-q["total_cycles"]
    with (npath.parent/"bank_aggregate.csv").open(newline="") as h:rs=list(csv.DictReader(h))
    tx=sum(int(r["transactions"]) for r in rs);waited=sum(int(r["transactions_with_cross_request_wait"]) for r in rs);ticks=sum(int(r["cross_request_bank_wait_ticks"]) for r in rs)
    return {"case":case,"config":label,"lanes4":l,"compute025":c,"outstanding1":o,"source":source,"normal_cycles":n["total_cycles"],"oracle_cycles":q["total_cycles"],"exposed_bank_cycles":d,"exposed_fraction":d/n["total_cycles"],"transactions":tx,"waited_transactions":waited,"waited_transaction_fraction":waited/tx,"cumulative_wait_ticks":ticks}

def main():
    SUITE.mkdir(parents=True,exist_ok=True)
    freeze={"cases":CASES,"new_configs":[tag(x) for x in CONFIGS],"reference_configs":["baseline","LCO"],"full_memory_trace":True,"pairing":"same DAG; oracle only toggles cross-request same-Bank timing","max_workers":2}
    (SUITE/"frozen_design.json").write_text(json.dumps(freeze,indent=2)+"\n")
    for case in CASES:
        for cfg in CONFIGS:prepare(case,cfg)
    jobs=[(case,cfg,mode) for case in CASES for cfg in CONFIGS for mode in ("normal","oracle")]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:status=list(pool.map(one,jobs))
    (SUITE/"launcher_status.json").write_text(json.dumps(status,indent=2)+"\n")
    if any(x["returncode"] for x in status):raise SystemExit(1)
    out=[]
    for case in CASES:
        # Existing no-factor baseline.
        n=BASE/"runs"/f"{case}_normal/validation.json";o=BASE/"runs"/f"{case}_oracle/validation.json"
        out.append(pair_row(case,"baseline",n,o,0,0,0,"bank_pressure_screen_v1"))
        for cfg in CONFIGS:
            label=tag(cfg);n=SUITE/"runs"/f"{case}_{label}_normal/validation.json";o=SUITE/"runs"/f"{case}_{label}_oracle/validation.json"
            out.append(pair_row(case,label,n,o,*cfg,"new_ablation"))
        # Existing all-three result.
        old=f"{case}_l4_c025";n=STRESS/"runs"/f"{old}_normal/validation.json";o=STRESS/"runs"/f"{old}_oracle/validation.json"
        out.append(pair_row(case,"LCO",n,o,1,1,1,"bank_memory_stress_v1"))
    with (SUITE/"ablation_results.csv").open("w",newline="") as h:
        w=csv.DictWriter(h,fieldnames=out[0].keys());w.writeheader();w.writerows(out)
    report={"status":"PASS","classification":"controlled synthetic memory-stress ablation","rows":out}
    (SUITE/"ablation_report.json").write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report,indent=2))
if __name__=="__main__":main()

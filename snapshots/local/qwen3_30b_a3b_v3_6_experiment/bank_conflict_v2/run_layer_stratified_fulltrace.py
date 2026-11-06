#!/usr/bin/env python3
import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
SUITE = ROOT / "results/bank_sampling_layer_stratified_v2"
LAYERS = [0, 8, 16, 24, 32, 40, 47]
LABELS = [("s4096", 4096), ("s1048576", 1048576), ("full", None)]
BINARY = ROOT / "toolchain/popnet_cross_request_release_v2/build_fulltrace_v4/popnet"
RAMULATOR = ROOT / "toolchain/ramulator2_cross_request_v1/libramulator.so"
RELEASE = ROOT / "results/bank_sampling_fulltrace_reference_v1/c8_simultaneous_release.csv"


def environment():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["HB_BANK_LOG_DETAIL"] = "0"
    return env


def prepare(layer, label, cap):
    graph = SUITE / "graphs" / f"layer{layer}_{label}"
    if (graph / "graph_manifest.json").exists():return graph
    command = [sys.executable, HERE / "build_arrival_sampling_graph.py", "--root", ROOT,
        "--context", 128, "--batch", 8, "--steps", 1, "--layer-start", layer,
        "--layers", 1, "--microbatch-size", 1, "--partition-capacity-mib", 512,
        "--cohort-policy", "exploratory_high_skew", "--cohort-repeat", 1,
        "--placement", ROOT / "results/sem_moe_reproduction_ctx128_v2/placement.json",
        "--compute-profile", ROOT / "scalesim_compute_profile_v1.json", "--hiband", "--out", graph]
    if cap is None:command.append("--full-memory-trace")
    else:command += ["--sample-bytes", cap]
    subprocess.run(list(map(str, command)), cwd=ROOT, env=environment(), check=True, stdout=subprocess.DEVNULL)
    return graph


def one(item):
    layer, label, cap = item
    graph = prepare(layer, label, cap)
    out = SUITE / "runs" / f"layer{layer}_{label}"
    validation = out / "validation.json"
    if validation.exists() and json.loads(validation.read_text()).get("status") == "PASS":return {"layer": layer, "label": label, "status": "SKIP_PASS"}
    command = [sys.executable, HERE / "run_arrival_sampling.py", "--root", ROOT,
        "--graph", graph, "--out", out, "--binary", BINARY,
        "--ramulator-library", RAMULATOR, "--request-releases", RELEASE,
        "--hiband", "--timeout-seconds", 1200]
    logs = SUITE / "launcher_logs";logs.mkdir(parents=True,exist_ok=True)
    with (logs / f"layer{layer}_{label}.log").open("w") as handle:
        result=subprocess.run(list(map(str,command)),cwd=ROOT,env=environment(),stdout=handle,stderr=subprocess.STDOUT)
    return {"layer":layer,"label":label,"status":"PASS" if result.returncode==0 else "FAIL","returncode":result.returncode}


def main():
    SUITE.mkdir(parents=True,exist_ok=True)
    jobs=[(layer,label,cap) for layer in LAYERS for label,cap in LABELS]
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for result in pool.map(one,jobs):print(json.dumps(result),flush=True);results.append(result)
    (SUITE/"launcher_status.json").write_text(json.dumps(results,indent=2)+"\n")
    if any(row["status"]=="FAIL" for row in results):raise SystemExit(1)


if __name__=="__main__":main()

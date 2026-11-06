#!/usr/bin/env python3
import argparse,csv,json
from pathlib import Path

SCHEMES=("baseline_ep","hiband","sem_moe","hiband_sem_moe")

def bank_stats(path):
    with path.open(newline="") as f:r=list(csv.DictReader(f))
    return {
        "transactions":len(r),
        "sum_queue_ticks":sum(int(x["controller_queue_ticks"]) for x in r),
        "sum_strict_wait_ticks":sum(int(x["cross_request_bank_wait_ticks"]) for x in r),
        "max_depart_tick":max(int(x["controller_depart_tick"]) for x in r),
    }

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--root",type=Path,required=True);ap.add_argument("--out",type=Path,required=True);a=ap.parse_args()
    report={"schema":"owner-shadow-paired-audit-v1","cases":{},"failures":[]}
    for s in SCHEMES:
        pair={m:a.root/s/m for m in ("normal","oracle")}
        launch={m:json.loads((p/"launch.json").read_text()) for m,p in pair.items()}
        val={m:json.loads((p/"validation.json").read_text()) for m,p in pair.items()}
        for key in ("binary_sha256","ramulator_library_sha256","graph_hashes","deepstack_timing_sha256"):
            if launch["normal"].get(key)!=launch["oracle"].get(key):report["failures"].append(f"{s}: {key} differs")
        nc=dict(launch["normal"]["controls"]);oc=dict(launch["oracle"]["controls"])
        oracle_flag=oc.pop("HB_IGNORE_CROSS_REQUEST_BANK_TIMING",None)
        if oracle_flag!="1":report["failures"].append(f"{s}: oracle flag missing")
        # Output paths necessarily differ and are not experimental inputs.
        nc.pop("HB_OUT",None);oc.pop("HB_OUT",None);nc.pop("POPNET_STATS_DIR",None);oc.pop("POPNET_STATS_DIR",None)
        if nc!=oc:report["failures"].append(f"{s}: non-intervention controls differ")
        stats={m:bank_stats(pair[m]/"bank_requests.csv") for m in pair}
        n=val["normal"]["total_cycles"];o=val["oracle"]["total_cycles"]
        report["cases"][s]={"normal_cycles":n,"oracle_cycles":o,"exposed_cross_request_bank_cycles":n-o,"exposed_fraction":(n-o)/n,"normal_bank":stats["normal"],"oracle_bank":stats["oracle"],"queue_tick_reduction":stats["normal"]["sum_queue_ticks"]-stats["oracle"]["sum_queue_ticks"],"max_depart_tick_reduction":stats["normal"]["max_depart_tick"]-stats["oracle"]["max_depart_tick"]}
    report["status"]="FAIL" if report["failures"] else "PASS"
    report["claim_boundary"]="exposed end-to-end sensitivity to an owner-isolated Bank timing/row-state oracle; not a realizable hardware configuration and not equal to summed request wait"
    a.out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n");print(json.dumps(report,indent=2,sort_keys=True));raise SystemExit(1 if report["failures"] else 0)
if __name__=="__main__":main()

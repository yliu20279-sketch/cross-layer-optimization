#!/usr/bin/env python3
"""Run immutable Qwen MoE cases through the integrated coupled LegoSim stack."""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--legosim-root",type=Path,required=True); ap.add_argument("--deepstack-root",type=Path,required=True); ap.add_argument("--deepstack-python",type=Path,required=True); ap.add_argument("--out",type=Path,required=True); ap.add_argument("--arch-tx-bytes",default="32"); a=ap.parse_args()
    here=Path(__file__).resolve().parent
    suite=a.legosim_root/"benchmark/whisper_operator_inventory/hiband_whisper_migration/step7_closure_cmd006"
    binary=suite/"popnet_coupled_src/build_coupled/popnet"
    required=[binary,a.deepstack_root,a.deepstack_python,here/"target_architecture_v3_6/ramulator2_hb_partition_v3_6_execution_overlay.yaml",here/"target_architecture_v3_6/deepstack_bank_oracle_v3_6_execution_overlay.json"]
    missing=[str(p) for p in required if not p.exists()]
    if missing: raise SystemExit("missing server dependencies: "+", ".join(missing))
    os.environ.update({
        "HB_EXECUTABLE":str(binary),
        "HB_RAM_CONFIG_TEMPLATE":str(here/"target_architecture_v3_6/ramulator2_hb_partition_v3_6_execution_overlay.yaml"),
        "HB_RAM_BASE_CHANNEL_WIDTH":"128","HB_RAM_BASE_ROWS":"16384","HB_ARCH_TX_BYTES":a.arch_tx_bytes,
        "HB_BASE_BYTES_PER_CYCLE":"25.6","DEEPSTACK_ROOT":str(a.deepstack_root),
        "DEEPSTACK_PYTHON":str(a.deepstack_python),
        "HB_DEEPSTACK_CONFIG":str(here/"target_architecture_v3_6/deepstack_bank_oracle_v3_6_execution_overlay.json")})
    sys.path.insert(0,str(suite)); import run_suite
    a.out=a.out.resolve()
    results=[]
    for name in ("ep_baseline","hiband_only","hiband_sem_moe"):
        results.append(run_suite.run(a.out,name,here/"generated/legosim"/name,{"HB_FIXED_MODE":"GLOBAL_BIAS"}))
    payload={"status":"PASS","scope":"synthetic-routing coupled-stack smoke; not a Qwen performance result","results":results,
             "binary_sha256":run_suite.sha(binary)}
    a.out.mkdir(parents=True,exist_ok=True); (a.out/"qwen_moe_smoke_summary.json").write_text(json.dumps(payload,indent=2)+"\n"); print(json.dumps(payload,indent=2))
if __name__=="__main__": main()

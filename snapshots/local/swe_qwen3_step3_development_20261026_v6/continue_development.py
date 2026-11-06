"""Finish registered dev observations; do not select another tiny seed until success."""
import json,traceback
from pathlib import Path
import backend as b
import run_repair as rr
ROOT=Path(__file__).resolve().parent

def main():
    tiny=json.loads((ROOT.parent/'swe_qwen3_step3_repair_20261026_v3/TINY_RESULT.json').read_text())
    equivalent=json.loads((ROOT.parent/'swe_qwen3_step3_repair_20261026_v4/PREFILL_EQUIVALENCE.json').read_text())
    assert tiny['state']=='PASS_TINY_AUTONOMOUS_LOOP' and equivalent['equal_tokens']
    attempts={}
    for name in ['swe_qwen3_step3_gpu_20261026_v1','swe_qwen3_step3_repair_20261026_v2','swe_qwen3_step3_repair_20261026_v3','swe_qwen3_step3_repair_20261026_v4','swe_qwen3_step3_repair_20261026_v5']:
        p=ROOT.parent/name/'TINY_RESULT.json'
        attempts[name]=json.loads(p.read_text())['state'] if p.exists() else 'NO_FINAL_RECEIPT'
    b.save(ROOT/'QUALIFICATION.json',dict(state='FUNCTIONAL_CHAIN_DEMONSTRATED_MODEL_ROBUSTNESS_NOT_PASSED',tiny_pass_reference='../swe_qwen3_step3_repair_20261026_v3/TINY_RESULT.json',all_prior_tiny_attempts=attempts,policy='Retain all success/failure; do not resample tiny until success; registered dev outcomes may fail and must be officially evaluated. This does not certify model solve ability.'))
    b.save(ROOT/'STATUS.json',dict(state='DEVELOPMENT_LOADING',NPU_runs=0))
    backend=b.Backend();backend.instrument();backend.decoding=dict(do_sample=True,temperature=0.7,top_p=0.8,top_k=20)
    b.save(ROOT/'STATUS.json',dict(state='DEVELOPMENT_RUNNING',NPU_runs=0))
    results=rr.development(backend)
    b.save(ROOT/'STATUS.json',dict(state='GENERATION_FINISHED_EVALUATION_PENDING',development=results,requests=len(backend.requests),NPU_runs=0))

if __name__=='__main__':
    try:main()
    except Exception:
        b.save(ROOT/'STATUS.json',dict(state='FAILED_RETAINED',traceback=traceback.format_exc(),NPU_runs=0));raise

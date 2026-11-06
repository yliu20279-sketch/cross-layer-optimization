import hashlib,json,shutil
from pathlib import Path
r=Path(__file__).resolve().parent
groups={
 'swe_qwen3_step3_gpu_20261026_v1':['TINY_RESULT.json','SHORT_GENERATION.json'],
 'swe_qwen3_step3_repair_20261026_v2':['FEEDBACK_AUDIT.json','CAPTURE_EQUIVALENCE.json','DECODING_CONTRAST.json','CAPTURE_AUDIT.json','TINY_RESULT.json','BASELINE_EVALUATION.json'],
 'swe_qwen3_step3_repair_20261026_v3':['TINY_RESULT.json','ADAPTER_REGRESSION.json','INTERRUPTION.json','marshmallow-code__marshmallow-1359/FAILURE.json','HOLDOUT_BOUNDARY.json'],
 'swe_qwen3_step3_repair_20261026_v4':['PREFILL_EQUIVALENCE.json','CHUNK_CACHE_CPU_CHECK.json','CAPTURE_AUDIT.json','TINY_RESULT.json'],
 'swe_qwen3_step3_repair_20261026_v5':['TINY_RESULT.json','guard_regression/RESULT.json']}
manifest=[]
for group,names in groups.items():
    for name in names:
        src=r.parent/group/name
        if not src.exists():continue
        dest=r/'diagnosis_receipts'/group/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
        manifest.append(dict(source=str(src),path=dest.relative_to(r).as_posix(),sha256=hashlib.sha256(dest.read_bytes()).hexdigest()))
(r/'DIAGNOSIS_RECEIPTS.json').write_text(json.dumps(manifest,indent=2))

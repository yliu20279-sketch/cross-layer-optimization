import json
from pathlib import Path
r=Path(__file__).resolve().parent
names=['swe_qwen3_step3_gpu_20261026_v1','swe_qwen3_step3_repair_20261026_v2','swe_qwen3_step3_repair_20261026_v3','swe_qwen3_step3_repair_20261026_v4','swe_qwen3_step3_repair_20261026_v5','swe_qwen3_step3_development_20261026_v6']
counts={name:sum((p.parent/'REQUEST.json').exists() for p in (r.parent/name/'requests').glob('*/MANIFEST.json')) for name in names}
counts['v6_diagnostic_followup']=sum((p.parent/'REQUEST.json').exists() for p in (r/'diagnostic_followup/requests').glob('*/MANIFEST.json'))
data=dict(unit='completed model.generate requests with REQUEST and MANIFEST, not independent tasks; interrupted partial requests excluded',phase_counts=counts,total_completed=sum(counts.values()))
(r/'PHASE_COUNTS.json').write_text(json.dumps(data,indent=2));print(json.dumps(data))

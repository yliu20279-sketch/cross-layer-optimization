import json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;P=R.parent/'swe_qwen3_step3_progress_20261027_v1'
relative=Path('inference/development_nonthinking/marshmallow-code__marshmallow-1343/requests')
records=[]
for old in sorted((P/relative).glob('*/REQUEST.json')):
    new=R/relative/old.parent.name/'REQUEST.json'
    if not new.exists():continue
    a=json.loads(old.read_text());b=json.loads(new.read_text())
    same_prompt=a['prompt_token_ids']==b['prompt_token_ids']
    records.append(dict(request=old.parent.name,same_prompt_tokens=same_prompt,
        generated_tokens_equal=a['new_token_ids']==b['new_token_ids'] if same_prompt else None,
        new_tokens_source=a['new_tokens'],new_tokens_candidate=b['new_tokens'],
        source_seconds=a['generation_wall_seconds'],candidate_seconds=b['generation_wall_seconds']))
result=dict(state='BOUNDED_CROSS_RUN_TOKEN_CHECK',records=records,
    scope='only compare completed requests with exact same prompt IDs; different warmup and isolated containers, not pure throughput/overhead comparison or arbitrary numerical certification')
(R/'PRIOR_DEVELOPMENT_TOKEN_COMPARISON.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

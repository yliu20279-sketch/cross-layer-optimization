import json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[1];P=R.parent/'swe_qwen3_step3_progress_20261027_v3'
relative=Path('inference/development_thinking/marshmallow-code__marshmallow-1343/requests/R0001/REQUEST.json')
a=json.loads((P/relative).read_text());b=json.loads((R/relative).read_text())
value=dict(state='BOUNDED_FIRST_PROPOSAL_COMPARISON',prompt_token_ids_equal=a['prompt_token_ids']==b['prompt_token_ids'],
    generated_token_ids_equal=a['new_token_ids']==b['new_token_ids'],new_tokens_v3=a['new_tokens'],new_tokens_v4=b['new_tokens'],
    mode_and_sampling_equal=a['thinking']==b['thinking'] and a['decoding']==b['decoding'],
    scope='one exact-prompt paired development proposal only; no general equivalence, throughput or population inference; v4 post-edit validation subsequently changes feedback')
(R/'FIRST_PROPOSAL_COMPARISON.json').write_text(json.dumps(value,indent=2));print(json.dumps(value,indent=2))

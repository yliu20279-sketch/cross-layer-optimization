"""Identity-only registration; this script never projects issue, gold or hidden test columns."""
import hashlib,json,datetime
from pathlib import Path
import pyarrow.parquet as pq
R=Path(__file__).resolve().parent;OLD=R.parent/'swe_qwen3_step3_gpu_20261026_v1'
used={x['instance_id'] for x in json.loads((OLD/'TASK_REGISTRATION.json').read_text())['tasks']}
columns=['instance_id','repo','base_commit','version']
rows=pq.read_table(OLD/'test.parquet',columns=columns).to_pylist()
seed='swe_qwen3_step3_progress_20261027_v1'
rows=sorted([t for t in rows if t['instance_id'] not in used],key=lambda t:hashlib.sha256((seed+'\n'+t['instance_id']).encode()).hexdigest())[:2]
out=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),state='IDENTITIES_ONLY_BODIES_UNREAD',columns=columns,
         selection='lowest SHA256(seed + newline + instance_id), test split excluding four used IDs',seed=seed,tasks=rows,
         gold_read=False,hidden_tests_read=False,problem_statement_read=False,conditional_on_development_gate=True)
(R/'NEW_HOLDOUT_REGISTRATION.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))

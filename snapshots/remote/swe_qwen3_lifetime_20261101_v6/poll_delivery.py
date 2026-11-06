import json
from pathlib import Path
R=Path(__file__).resolve().parent
failures=['RAW_ORACLE_FAILURE.txt','LIVE_CACHE_FAILURE.txt','STREAM_COLLECTOR_FAILURE.txt','CPU_STATS_SNAPSHOT_FAILURE.txt']
for n in failures:
 if (R/n).exists():print(json.dumps(dict(state='FAILED',file=n,reason=(R/n).read_text()[-2000:])));raise SystemExit
if (R/'RUN_EXIT.json').exists():
 s=json.loads((R/'RUN_EXIT.json').read_text())
 if s['returncode']!=0 or s.get('reason'):print(json.dumps(dict(state='FAILED',run=s)));raise SystemExit
if (R/'QUEUE_STATUS.json').exists():
 q=json.loads((R/'QUEUE_STATUS.json').read_text())
 if q['state']=='NOT_STARTED_BASELINE_OR_QUEUE_GATE_FAILED':print(json.dumps(dict(state='FAILED',queue=q)));raise SystemExit
if (R/'SAFE_DELIVERY_STATUS.json').exists():print((R/'SAFE_DELIVERY_STATUS.json').read_text())
else:print(json.dumps(dict(state='PENDING',scope=R.name)))

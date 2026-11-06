"""Independent local reconstruction of the final small backend receipt."""
from pathlib import Path
import csv
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.common import require,file_hash
receipt=json.loads((ROOT/'evidence/REAL_CONTROL_PROBE_02.json').read_text())
D=ROOT/'remote_control_02/control_probe_02'
for name,sha in receipt['artifacts'].items():require(file_hash(D/name)==sha,'raw probe member changed: '+name)
events=list(csv.DictReader((D/'out/events.csv').open()))
pending={};seen=set();noc=set();noc_done=set()
for event in events:
    kind=event['event']
    if kind in ('DRAM_ISSUE','DRAM_DONE'):
        key=tuple(event[k] for k in ('region','token','rank'))
        payload=tuple(event[k] for k in ('address','bytes','write'))
        time=float(event['time'])
        if kind=='DRAM_ISSUE':
            require(key not in seen,'reused transaction');seen.add(key);pending[key]=(time,payload)
        else:
            require(key in pending,'unknown callback');accepted,original=pending.pop(key)
            require(time>=accepted and payload==original,'callback identity/time differs')
    elif kind=='NOC_ISSUE':
        require(event['token'] not in noc,'reused packet');noc.add(event['token'])
    elif kind=='NOC_DONE':
        require(event['token'] in noc and event['token'] not in noc_done,'duplicate/unknown packet callback')
        noc_done.add(event['token'])
require(not pending and len(seen)==3 and noc==noc_done,'undrained native probe')
addresses=sorted([int(e['address']),int(e['bytes'])] for e in events if e['event']=='DRAM_ISSUE' and e['write']=='0')
require(addresses==[[8,16],[8186,6]],'new map not consumed')
result={'status':'PASS_LOCAL_INDEPENDENT_RAW_CONTROL_AUDIT','transactions':len(seen),'packets':len(noc),
        'actual_read_addresses':addresses,'probe_artifact_sha_verified':len(receipt['artifacts']),
        'full_layer_or_performance_claim':False}
(ROOT/'evidence/LOCAL_CONTROL_AUDIT.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))

"""Preserve every diagnostic record; distinguish physical traffic domains."""
import collections,csv,hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parent/'unified_layers'
rows=[list(map(int,line.split())) for line in (R/'run1/bench.txt').read_text().splitlines()]
domains=collections.defaultdict(list)
for line in rows:
 assert len(line)==6
 pair={line[2],line[3]}
 if pair=={1,2}:domain='diagnostic_HB_RPC_not_canonical_horizontal_NoC'
 elif pair=={0,1}:domain='CPU_NPU_activation'
 else:domain='other_control'
 domains[domain].append(line)
assert sum(map(len,domains.values()))==len(rows)
tx=list(csv.DictReader((R/'case1/npusim_dram_transactions_1_0.csv').open()))
payload=sum(int(t['bytes']) for t in tx)
out=dict(state='DOMAIN_AUDIT_ONLY_NOT_TARGET_REPLAY',records=len(rows),domains={k:dict(records=len(v),diagnostic_flits=sum(a[4] for a in v)) for k,v in domains.items()},HB_payload_bytes=payload,HB_minimum_serial_service_cycles=(payload*5+127)//128,service_scope='derived 128bytes/5cycles occupancy only; not fixed latency or measured complete runtime',canonical_source='whisper_operator_inventory/target_architecture_v3_6/target_architecture_v3_6.yaml: hybrid_bonding.traffic_trace_separate_from_horizontal_popnet=true',bench_sha256=hashlib.sha256((R/'run1/bench.txt').read_bytes()).hexdigest(),records_removed=0,conclusion='Diagnostic all-RPC PopNet completion cannot certify canonical V3.6 timing. No target delay is synthesized by this classifier.')
(R.parent/'TRACE_DOMAIN_AUDIT.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))

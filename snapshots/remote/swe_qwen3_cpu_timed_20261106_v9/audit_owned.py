import json,hashlib,struct,sys
from pathlib import Path
R=Path(__file__).resolve().parent;V=R.parent/'swe_qwen3_lifetime_20261101_v6';D=R/(sys.argv[1] if len(sys.argv)>1 else 'control_replay')
j=lambda p:json.loads(p.read_text())
# Reuse the independent allocation, full payload checksum and source-stage audit.
s=(R/'allocation_audit_source.py').read_text().replace("('final_CPU_return',-1)","('final_CPU_return_and_session_close',-1)")
s=s.replace("assert j(R/'ALLOCATOR_CONTROLS.json')['state']=='PASS_LIMITED_C_ALLOCATOR_CONTROLS'","assert 'PASS_CPU_ONLY_OWNER_CONTROLS' in (R/'OWNER_CONTROLS.log').read_text()")
(R/'audit_allocation_payloads.py').write_text(s)
exec(compile(s,str(R/'audit_allocation_payloads.py'),'exec'),dict(__file__=str(R/'audit_allocation_payloads.py')))
nodes=j(D/'NODES.json');events=j(D/'KV_OWNERSHIP_EVENTS.json');services=j(D/'CPU_SERVICES.json');kv=j(D/'KV_EVENTS.json') if (D/'KV_EVENTS.json').exists() else None
pins={};owned=[s for s in services if s['kind'] in [27,28]]
assert len(events)==len(owned)==16
for e,s in zip(events,owned):
 n=nodes[e['node']];before=pins.get(n['id'],0);after=before+(1 if e['retain'] else -1)
 assert after>=0 and after==e['pins'] and e['start']>=e['required_ready']
 assert e['version']==n['allocation_version'] and e['complete']<=n['retired_at']
 assert s['kind']==(27 if e['retain'] else 28) and (s['a'],s['b'])==(n['id'],e['version'])
 payload=struct.pack('<QQQQ',n['offset'],e['version'],after,0)
 assert s['output_sha256']==hashlib.sha256(payload).hexdigest() and (s['start'],s['complete'])==(e['start'],e['complete'])
 pins[n['id']]=after
assert not any(pins.values()) and sum(e['reason']=='explicit_session_close' for e in events)==4
for i in pins:
 es=[e for e in events if e['node']==i];assert es[0]['retain'] and not es[-1]['retain']
 assert nodes[i]['last_consumer_barrier_start']>=es[-1]['complete']
 # Every intervening layer barrier must leave owned KV alive.
 for b in j(D/'LIFETIME_EVENTS.json'):
  if b['kind']=='barrier' and es[0]['complete']<=b['start']<es[-1]['start']:assert nodes[i]['retired_at']>b['complete']
inspection=[s for s in services if s['kind']==29];assert len(inspection)==1
assert inspection[0]['output_sha256']==hashlib.sha256(struct.pack('<QQQQ',0,0,0,208*2**20)).hexdigest()
assert j(D/'ARENA_FINAL.json')==dict(live_nodes=0,live_bytes=0,pins=0,free_bytes=208*2**20,endpoint_acknowledged=True)
native=D.name in ['case1','case2']
out=j(D/'LIFETIME_AUDIT.json') if native else j(R/'LIFETIME_CONTROL_AUDIT_V2.json')
if native:assert j(D/'CPU_TEARDOWN_PASS.json')['state']=='PASS_EMPTY_ARENA_ACK'
out.update(state='PASS_LIMITED_NATIVE_TWO_LAYER_KV_OWNERSHIP' if native else 'PASS_LIMITED_CPU_TWO_LAYER_KV_OWNERSHIP',ownership_events=len(events),session_close_unpins=4,endpoint_ack_scope='actual endpoint acknowledgement' if native else 'CPU-only test double; real endpoint smoke audited separately')
((D/'OWNED_AUDIT.json') if native else (R/'OWNED_CONTROL_AUDIT.json')).write_text(json.dumps(out,indent=2));print(json.dumps(out))

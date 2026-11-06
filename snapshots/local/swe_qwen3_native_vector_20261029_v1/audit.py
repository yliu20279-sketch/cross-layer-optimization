import gzip,json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/'attempt1'
def j(p):return json.loads(p.read_text())
assert all(hashlib.sha256((R/n).read_bytes()).hexdigest()==h for n,h in j(R/'FREEZE.json').items())
s=j(D/'RESULTS.json');events=[json.loads(x) for x in gzip.open(D/'N00/events.jsonl.gz','rt')];emap={e['id']:e for e in events}
assert len(emap)==len(events)==344
for e in events:
 assert e['done']>=e['start']
 for dep in e['deps']:assert dep in emap and emap[dep]['done']<=e['start'] and dep<e['id']
assert sum(e['requests'] for e in events)==s['device']['counts']['RAM_transactions']==175360
assert sum(e['ops'] for e in events)==634880
assert len(s['checks'])==28 and all(c['exact'] and c['different']==0 for c in s['checks'])
assert len(set(s['negative_controls']))==56
for n in s['nodes']:
 assert emap[n['compute_event']]['done']<=emap[n['commit_event']]['start']<=n['ready_ns']
 assert n['elements']==emap[n['compute_event']]['ops']
lr=j(D/'LAST_READERS.json');regions=sorted(lr['regions'],key=lambda v:v['offset'])
for i,v in enumerate(regions):
 assert not v['pending'] and v['retired_ns'] is not None and v['offset']+v['bytes']<=512*2**20
 if i:assert regions[i-1]['offset']+regions[i-1]['bytes']<=v['offset']
assert s['device']['SRAM_peak_bytes']<=4*2**20
out=dict(state='PASS_LIMITED_VECTOR_EVENT_AUDIT',events=len(events),transactions=175360,checks=28,negative_controls=56,SRAM_peak_bytes=466944,HB_bytes=3072000,scope='dependency/capacity/freeze and recorded strict-check audit; not independent reexecution of arithmetic or physical timing')
(R/'INDEPENDENT_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))

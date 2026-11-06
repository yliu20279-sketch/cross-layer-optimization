import csv, hashlib, json, sys
from pathlib import Path
from core.coupled_backend import LiveBackend
root=Path.cwd()
out=Path(sys.argv[1]).resolve()
build=json.loads((root/'evidence/COUPLED_BUILD_04.json').read_text())
b=LiveBackend(build['binary'],build['sha256'],out/'backend',root/'ramulator32.yaml',timeout=30)
try:
    a,c=[b.rpc(12,i,256,i+1)[2] for i in range(2)]
    payloads=[bytes(range(256)),bytes(reversed(range(256)))]
    for i,(h,data) in enumerate(zip((a,c),payloads),1):
        assert b.rpc(2,h,0,256,i,payload=data)[3]==256
    assert b.rpc(13,a,1,c,2)[3]==512
    raw=b._read(512)
    assert raw==b''.join(payloads)
    checked=b.clock
    consumer_start=b.clock
    result=[sum(raw[:256]),sum(raw[256:])]
    assert result==[32640,32640]
    rows=list(csv.reader((out/'backend/KV_BATCH.csv').open()))
    assert len(rows)==32
    issue,done=rows[:16],rows[16:]
    assert all(x[0]=='issue' for x in issue) and all(x[0]=='complete' for x in done)
    assert sorted(x[2:] for x in issue)==sorted(x[2:] for x in done)
    assert len({x[4] for x in issue})==16 and sorted(x[2] for x in issue)==['1']*8+['2']*8
    assert all(float(x[1])<100000 for x in rows)
    last=max(float(x[1]) for x in done)
    assert last<=checked<=consumer_start
    for i,h in enumerate((a,c),1): assert b.rpc(4,h,i)[3]==1
    b.close()
    (out/'RESULT.json').write_text(json.dumps(dict(status='PASS_LIMITED_DIAGNOSTIC_CONSUMER',last_callback_ns=last,checked_ns=checked,consumer_start_ns=consumer_start,payload_sha256=hashlib.sha256(raw).hexdigest(),consumer_result=result,step3_B='PARTIAL_NOT_FROZEN')))
finally:
    if not b.closed: b.abort()

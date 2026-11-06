import csv
import json
from pathlib import Path
from core.coupled_backend import LiveBackend

root=Path(__file__).resolve().parent
def read(path):
    return json.loads(path.read_text())
build=read(root/'evidence/COUPLED_BUILD_04.json')
launch=json.loads(next(x['text'] for x in read(root/'evidence/NATIVE_SOURCE_INPUTS.json')
                       if x['path'].endswith('backend_launch.json')))
for model,ranks in [('qwen3',(0,1)),('qwen15',(0,0))]:
    out=root/f'{model}_native_probe'
    backend=LiveBackend(build['binary'],build['sha256'],out,launch['controls']['HB_RAM_CONFIG'],timeout=60)
    try:
        a=backend.rpc(12,ranks[0],4096,1)[2]
        b=backend.rpc(12,ranks[1],4096,2)[2]
        for handle,owner,byte in [(a,1,b'A'),(b,2,b'B')]:
            assert backend.rpc(2,handle,0,4096,owner,payload=byte*4096)[3]==4096
        clock=backend.clock
        for handle,other in [(a,2),(b,1)]:
            assert backend.rpc(3,handle,0,256,other)[3]==0
            assert backend.rpc(2,handle,0,256,other,payload=b'Z'*256)[3]==0
            assert backend.rpc(4,handle,other)[3]==0
        assert backend.clock==clock
        assert backend.rpc(13,a,1,b,2)[3]==512
        assert backend._read(512)==b'A'*256+b'B'*256
        for handle,owner,byte in [(a,1,b'A'),(b,2,b'B')]:
            assert backend.rpc(3,handle,0,4096,owner)[3]==4096
            assert backend._read(4096)==byte*4096
            assert backend.rpc(4,handle,owner)[3]==1
        summary=backend.close()
        batch=list(csv.reader((out/'KV_BATCH.csv').open()))
        denied=list(csv.reader((out/'KV_DENIED.csv').open()))
        assert len(denied)==6 and len({(r[3],r[4]) for r in denied})==1
        assert len(batch)==4 and {r[2] for r in batch if r[0]=='issue'}=={'1','2'}
        assert max(float(r[1]) for r in batch if r[0]=='issue')<min(float(r[1]) for r in batch if r[0]=='complete')
        (out/'RESULT.json').write_text(json.dumps({'status':'PASS_LIMITED_NATIVE_KV_PROBE',
            'model_label':model,'ranks':ranks,'events':batch,'rejected':denied,'summary':summary,
            'frozen_model_execution':False,'formal_performance':False},indent=2))
    finally:
        if not backend.closed:
            backend.abort()

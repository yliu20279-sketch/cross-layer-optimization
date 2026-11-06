"""Bounded live KV service ownership probe. Never a performance run."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from core.coupled_backend import LiveBackend

class OwnedKV:
    def __init__(self, backend):
        self.backend=backend
        self.owners={}

    def stage(self, request, rank, payload):
        handle=self.backend.stage(rank,payload)
        self.owners[handle]=request
        return handle

    def authorize(self, request, handle):
        if not request or self.owners.get(handle)!=request:
            raise PermissionError("KV handle is outside the request ownership domain")

    def read(self, request, handle):
        self.authorize(request,handle)
        return self.backend.get(handle)

    def release(self, request, handle):
        self.authorize(request,handle)
        self.backend.free(handle)
        del self.owners[handle]

def read(path):
    return json.loads(path.read_text())
build=read(ROOT/'evidence/COUPLED_BUILD_04.json')
launch=json.loads(next(x['text'] for x in read(ROOT/'evidence/NATIVE_SOURCE_INPUTS.json')
                       if x['path'].endswith('backend_launch.json')))
out=ROOT/'owned_kv_probe01'
assert not out.exists()
backend=LiveBackend(build['binary'],build['sha256'],out,launch['controls']['HB_RAM_CONFIG'],timeout=60)
service=OwnedKV(backend)
try:
    a=service.stage('A',0,b'A'*4096)
    b=service.stage('B',0,b'B'*4096)
    rejected=[]
    for action,request,handle in ((service.read,'A',b),(service.read,'B',a),
                                  (service.release,'A',b),(service.release,'B',a)):
        old=(len(backend.events),backend.clock)
        try:
            action(request,handle)
        except PermissionError:
            assert old==(len(backend.events),backend.clock)
            rejected.append({'operation':action.__name__,'request':request,'handle':handle})
        else:
            raise RuntimeError('cross-request access was accepted')
    assert service.read('A',a)==b'A'*4096
    assert service.read('B',b)==b'B'*4096
    service.release('A',a)
    service.release('B',b)
    summary=backend.close()
    (out/'RESULT.json').write_text(json.dumps({'status':'PASS_LIMITED_SERVICE_PROBE',
        'rejects':rejected,'direct_backend_acl_verified':False,'full_layer_integration':False,
        'summary':summary,'formal_performance':False},indent=2))
except BaseException:
    if not backend.closed:
        backend.abort()
    raise

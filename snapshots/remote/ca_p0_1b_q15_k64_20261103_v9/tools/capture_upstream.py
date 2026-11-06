"""Read selected frozen service sources; never launch or alter upstream work."""
from pathlib import Path
import hashlib
import io
import json
import tarfile
R=Path('/mnt/sda1/h3240101068/swe_qwen3_lifetime_owned_20261102_v8')
D=Path('/mnt/sda1/h3240101068/ca_semmoe_hiband_coupled_20261102_v5')
D.mkdir(exist_ok=True)
freeze=json.loads((R/'FREEZE.json').read_text())
names=['bridge_full.cpp','sram_matrix.h','full_adapter.py','integrated_adapter.py','owned_adapter.py',
       'worker.py','cpu_services.h','unified_full.yml','gateway.cpp','peer.py','cache_evict.h',
       'BRIDGE_BUILD_COMMAND.json','CPU_BUILD_COMMAND.json','preflight.py','noc_v3_6.gv',
       'EXTERNAL_DEPENDENCIES.json','FREEZE.json','PARAMETERS.json','HOST_BACKING.json']
rows=[]
with tarfile.open(D/'UPSTREAM_SOURCE.tar.gz','w:gz') as tar:
    for name in names:
        p=R/name
        if not p.is_file():rows.append({'name':name,'status':'MISSING'});continue
        assert p.stat().st_size<4*1024**2,('unexpected selected source size',name)
        payload=p.read_bytes();sha=hashlib.sha256(payload).hexdigest()
        expected=freeze.get(name)
        if expected is not None:assert expected==sha,('upstream freeze changed',name)
        rows.append({'name':name,'path':str(p),'sha256':sha,'bytes':len(payload),'freeze_sha256':expected,
                     'status':'MATCH' if expected else 'HASHED_NO_EXPECTED'})
        info=tarfile.TarInfo('upstream/'+name);info.size=len(payload);tar.addfile(info,io.BytesIO(payload))
    record={'source_root':str(R),'scope':'selected source only, no upstream job state or execution',
            'files':rows,'native_runs':0}
    raw=json.dumps(record,indent=2).encode();info=tarfile.TarInfo('upstream/SOURCE_CAPTURE.json');info.size=len(raw);tar.addfile(info,io.BytesIO(raw))
print(json.dumps({'captured':len(rows),'status_counts':{k:sum(r['status']==k for r in rows) for k in ('MATCH','HASHED_NO_EXPECTED','MISSING')}}))

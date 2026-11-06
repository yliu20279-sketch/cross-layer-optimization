"""Release only reproducible uncompressed temporary layers unique to interrupted new-image fetch."""
import json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent
C=(R.parent/'swe_qwen3_step3_gpu_20261026_v1/registry_cache').resolve()
current=C/'matplotlib__matplotlib-25442.manifest.json'
def ids(manifest):
    value=json.loads(manifest.read_text());key=value['config']['digest'].split(':')[1]
    config=C/(key+'.json')
    return json.loads(config.read_text())['rootfs']['diff_ids'] if config.exists() else []
protected=set()
for p in C.glob('*.manifest.json'):
    if p!=current:protected.update(ids(p))
released=[]
for diff in ids(current):
    if diff in protected:continue
    digest=diff.split(':')[1];p=(C/(digest+'.layer.tar')).resolve()
    assert p.parent==C and len(digest)==64
    if not p.exists():continue
    h=hashlib.sha256()
    with p.open('rb') as f:
        while chunk:=f.read(8*1024*1024):h.update(chunk)
    assert h.hexdigest()==digest
    released.append(dict(path=str(p),bytes=p.stat().st_size,sha256=digest));p.unlink()
receipt=dict(state='DERIVED_TEMP_ONLY_RELEASED',files=released,bytes=sum(x['bytes'] for x in released),
    preserved='all verified compressed blobs, manifests, configs, existing other-image references, weights and evidence')
(R/'CACHE_DERIVED_RELEASE.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(dict(state=receipt['state'],bytes=receipt['bytes'])))

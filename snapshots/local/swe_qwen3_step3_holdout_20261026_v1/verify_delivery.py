"""Local streaming verification; no torch import and no extraction."""
import hashlib,json,tarfile
from pathlib import Path,PurePosixPath
R=Path(__file__).resolve().parent
archive=R/'EVIDENCE.tar.gz'
h=hashlib.sha256()
with archive.open('rb') as f:
    while block:=f.read(8*1024*1024):h.update(block)
assert h.hexdigest()==(R/'EVIDENCE.sha256').read_text().split()[0]
actual={};manifest=None
with tarfile.open(archive,'r|gz') as t:
    for m in t:
        assert m.isfile() and not PurePosixPath(m.name).is_absolute() and '..' not in PurePosixPath(m.name).parts
        assert m.name not in actual
        f=t.extractfile(m)
        if m.name=='FILE_MANIFEST.json':manifest=json.load(f);continue
        digest=hashlib.sha256();count=0
        while block:=f.read(8*1024*1024):digest.update(block);count+=len(block)
        actual[m.name]=dict(bytes=count,sha256=digest.hexdigest())
assert manifest is not None and set(actual)=={x['path'] for x in manifest}
for item in manifest:assert actual[item['path']]==dict(bytes=item['bytes'],sha256=item['sha256'])
result=dict(state='PASS_ALL_DELIVERED_MEMBERS_SHA256',archive_bytes=archive.stat().st_size,archive_sha256=h.hexdigest(),payload_files=len(actual),payload_bytes=sum(x['bytes'] for x in actual.values()),scope='local byte integrity, no extraction or local numeric recertification')
(R/'LOCAL_EVIDENCE_VERIFICATION.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))

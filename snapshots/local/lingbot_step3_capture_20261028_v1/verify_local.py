import pathlib,hashlib,tarfile,json
from pathlib import PurePosixPath
P=pathlib.Path(__file__).resolve().parent
a=P/'compact_evidence.tar.gz'
expected=(P/'compact_evidence.tar.gz.sha256').read_text().split()[0]
assert hashlib.sha256(a.read_bytes()).hexdigest()==expected
D=P/'server_evidence';D.mkdir(exist_ok=True)
with tarfile.open(a) as t:
    for m in t.getmembers():
        path=PurePosixPath(m.name)
        assert not path.is_absolute() and '..' not in path.parts and m.isfile(),m.name
        q=D.joinpath(*path.parts);q.parent.mkdir(parents=True,exist_ok=True)
        with t.extractfile(m) as src:q.write_bytes(src.read())
manifest=json.loads((D/'COMPACT_MANIFEST.json').read_text())
for name,row in manifest['files'].items():
    q=D/name
    assert q.stat().st_size==row['bytes'] and hashlib.sha256(q.read_bytes()).hexdigest()==row['sha256'],name
result=dict(status='PASS_COMPACT_ARCHIVE_AND_ALL_INCLUDED_MEMBERS',archive_sha256=expected,archive_bytes=a.stat().st_size,verified_members=len(manifest['files']),verified_bytes=manifest['local_bytes'],full_raw_transferred=False,full_remote_members=manifest['full_remote_members'],full_remote_bytes=manifest['full_remote_bytes'],scope=manifest['scope'])
(P/'LOCAL_VERIFICATION.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps(result))

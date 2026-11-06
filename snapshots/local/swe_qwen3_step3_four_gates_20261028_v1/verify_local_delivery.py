import hashlib,json,tarfile
from pathlib import Path,PurePosixPath
R=Path(__file__).resolve().parent
def sha(data):return hashlib.sha256(data).hexdigest()
d=json.loads((R/'DELIVERY.json').read_text());a=R/'EVIDENCE.tar.gz'
assert a.stat().st_size==d['archive_bytes'] and sha(a.read_bytes())==d['archive_sha256']
seen=set();total=0;manifest=None
with tarfile.open(a,'r:gz') as t:
 for member in t:
  assert member.isfile();name=PurePosixPath(member.name);assert not name.is_absolute() and '..' not in name.parts
  content=t.extractfile(member).read()
  if member.name=='FILE_MANIFEST.json':
   manifest={x['path']:x for x in json.loads(content)};(R/'FILE_MANIFEST.json').write_bytes(content);continue
  assert manifest is not None and member.name in manifest and member.name not in seen
  item=manifest[member.name];assert len(content)==item['bytes'] and sha(content)==item['sha256']
  p=R.joinpath(*name.parts);assert p.resolve().is_relative_to(R.resolve())
  if p.exists():assert p.is_file() and p.read_bytes()==content,'Preserve distinct local file: '+member.name
  else:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(content)
  seen.add(member.name);total+=len(content)
assert seen==set(manifest) and len(seen)==d['payload_files'] and total==d['payload_bytes']
receipt=dict(state='PASS_OUTER_AND_ALL_MEMBERS_SHA256',archive_sha256=d['archive_sha256'],archive_bytes=d['archive_bytes'],payload_files=len(seen),payload_bytes=total,scope='local integrity only; independent event audit is separate')
(R/'LOCAL_DELIVERY_VERIFICATION.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))

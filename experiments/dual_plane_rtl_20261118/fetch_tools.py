"""Download the pinned, upstream sv2v binary for Linux structural checks."""
import hashlib,io,json,urllib.request,zipfile
from pathlib import Path
R=Path(__file__).resolve().parent
def main():
    p=json.loads((R/'tools/SV2V_PROVENANCE.json').read_text())
    blob=urllib.request.urlopen(p['url'],timeout=120).read()
    assert hashlib.sha256(blob).hexdigest()==p['archive_sha256'],'sv2v archive hash mismatch'
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names=[n for n in z.namelist() if n.endswith('/sv2v') or n=='sv2v'];assert len(names)==1
        binary=z.read(names[0])
    assert hashlib.sha256(binary).hexdigest()==p['binary_sha256']
    dest=R/'tools/sv2v';dest.write_bytes(binary);dest.chmod(0o755)
    print('Verified sv2v 0.0.13:',p['binary_sha256'])
if __name__=='__main__':main()
